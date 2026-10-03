package nl.zennay.raiseai

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.util.Locale
import java.util.concurrent.Executors

class NativeVoiceActivity : Activity(), RecognitionListener {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()

    private lateinit var statusText: TextView
    private lateinit var transcriptText: TextView
    private lateinit var detailText: TextView
    private lateinit var orb: View
    private lateinit var fallbackButton: Button

    private var recognizer: SpeechRecognizer? = null
    private var orbAnimator: ObjectAnimator? = null
    private var submitted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(buildUi())
        setState("starting", "Klaarmaken…")

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        } else {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_AUDIO &&
            grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        } else {
            showError("Microfoon-toegang is nodig")
        }
    }

    private fun buildUi(): View {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(28), dp(24), dp(24))
            setBackgroundColor(Color.BLACK)
        }

        statusText = textView(17f, Color.WHITE)
        column.addView(statusText, fullWidth(bottom = 16))

        orb = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(
                    Color.rgb(71, 115, 255),
                    Color.rgb(177, 82, 255),
                    Color.rgb(51, 210, 193)
                )
            ).apply {
                shape = GradientDrawable.OVAL
            }
        }
        column.addView(orb, LinearLayout.LayoutParams(dp(88), dp(88)).apply {
            bottomMargin = dp(18)
        })

        transcriptText = textView(16f, Color.WHITE).apply {
            text = "Zeg iets…"
        }
        column.addView(transcriptText, fullWidth(bottom = 10))

        detailText = textView(12f, Color.LTGRAY)
        column.addView(detailText, fullWidth(bottom = 14))

        fallbackButton = Button(this).apply {
            text = "Open Gemini fallback"
            isAllCaps = false
            visibility = View.GONE
            setOnClickListener {
                AssistantLauncher.launchFromActivity(this@NativeVoiceActivity)
                finish()
            }
        }
        column.addView(fallbackButton, fullWidth())

        return column
    }

    private fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            showError("Spraakherkenning is niet beschikbaar")
            return
        }

        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).also {
            it.setRecognitionListener(this)
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "nl-NL")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(
                RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS,
                1_000L
            )
        }

        submitted = false
        setState("listening", "Ik luister")
        recognizer?.startListening(intent)
    }

    override fun onReadyForSpeech(params: Bundle?) {
        setState("listening", "Ik luister")
    }

    override fun onBeginningOfSpeech() {
        setState("listening", "Praat maar")
    }

    override fun onRmsChanged(rmsdB: Float) {
        val scale = (1f + (rmsdB.coerceIn(0f, 10f) / 45f))
        orb.scaleX = scale
        orb.scaleY = scale
    }

    override fun onBufferReceived(buffer: ByteArray?) = Unit

    override fun onEndOfSpeech() {
        setState("understanding", "Even denken…")
    }

    override fun onError(error: Int) {
        if (submitted) return
        val retryable = error == SpeechRecognizer.ERROR_NO_MATCH ||
            error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT

        if (retryable) {
            transcriptText.text = "Ik hoorde niets"
            mainHandler.postDelayed({ startListening() }, 700L)
        } else {
            showError("Spraakherkenning fout: $error")
        }
    }

    override fun onResults(results: Bundle?) {
        val text = bestResult(results)
        if (text.isNullOrBlank()) {
            showError("Geen transcript ontvangen")
            return
        }
        submit(text)
    }

    override fun onPartialResults(partialResults: Bundle?) {
        bestResult(partialResults)?.takeIf { it.isNotBlank() }?.let {
            transcriptText.text = it
        }
    }

    override fun onEvent(eventType: Int, params: Bundle?) = Unit

    private fun bestResult(bundle: Bundle?): String? =
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
            ?.trim()

    private fun submit(text: String) {
        if (submitted) return
        submitted = true
        recognizer?.stopListening()
        transcriptText.text = text

        val settings = GatewayConfig.load(this)
        if (settings == null) {
            WatchE2eEvidence.recordFailure(
                context = this,
                inputLengthChars = text.length,
                latencyMs = 0L,
                errorCode = "gateway_not_configured"
            )
            showError("VPS-gateway is nog niet gekoppeld")
            detailText.text = "Native voice werkt; gateway-config ontbreekt nog."
            return
        }

        setState("sending", "Naar je VPS…")
        val requestStartedMs = SystemClock.elapsedRealtime()

        io.execute {
            runCatching { GatewayClient(settings).send(text) }
                .onSuccess { response ->
                    val latencyMs = SystemClock.elapsedRealtime() - requestStartedMs
                    WatchE2eEvidence.recordSuccess(
                        context = applicationContext,
                        inputLengthChars = text.length,
                        latencyMs = latencyMs,
                        response = response
                    )
                    mainHandler.post {
                        val backgroundAction =
                            response.executionEnabled &&
                                response.answer == null &&
                                response.route in setOf("zcloud_task", "smart_home")

                        setState(
                            if (backgroundAction) "executing" else "replying",
                            when {
                                backgroundAction -> "Wordt uitgevoerd"
                                response.answer != null -> "Antwoord"
                                else -> "Route klaar"
                            }
                        )

                        detailText.text = response.answer ?: buildString {
                            append("Route: ")
                            append(response.route)
                            if (!response.executionEnabled) {
                                append("\nConnector: ")
                                append(response.executionReason ?: "nog niet gekoppeld")
                            }
                        }
                        fallbackButton.visibility = View.GONE
                    }
                }
                .onFailure { error ->
                    val latencyMs = SystemClock.elapsedRealtime() - requestStartedMs
                    WatchE2eEvidence.recordFailure(
                        context = applicationContext,
                        inputLengthChars = text.length,
                        latencyMs = latencyMs,
                        error = error
                    )
                    mainHandler.post {
                        showError("VPS niet bereikbaar")
                        detailText.text = error.message ?: "Onbekende netwerkfout"
                    }
                }
        }
    }

    private fun setState(state: String, label: String) {
        NativeSessionState.set(state)
        statusText.text = label

        if (state == "listening" || state == "sending" || state == "executing") {
            if (orbAnimator?.isRunning != true) {
                orbAnimator = ObjectAnimator.ofPropertyValuesHolder(
                    orb,
                    PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.12f),
                    PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.12f)
                ).apply {
                    duration = 800L
                    repeatMode = ObjectAnimator.REVERSE
                    repeatCount = ObjectAnimator.INFINITE
                    start()
                }
            }
        } else {
            orbAnimator?.cancel()
            orb.animate().scaleX(1f).scaleY(1f).setDuration(160L).start()
        }
    }

    private fun showError(message: String) {
        NativeSessionState.set("error")
        statusText.text = message
        orbAnimator?.cancel()
        fallbackButton.visibility = View.VISIBLE
    }

    private fun textView(size: Float, color: Int): TextView =
        TextView(this).apply {
            textSize = size
            setTextColor(color)
            gravity = Gravity.CENTER
        }

    private fun fullWidth(bottom: Int = 0): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            bottomMargin = dp(bottom)
        }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        orbAnimator?.cancel()
        recognizer?.cancel()
        recognizer?.destroy()
        io.shutdownNow()
        NativeSessionState.set("idle")
        super.onDestroy()
    }

    companion object {
        private const val REQUEST_AUDIO = 201
    }
}