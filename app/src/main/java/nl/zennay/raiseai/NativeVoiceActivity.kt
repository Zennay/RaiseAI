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
import android.speech.tts.TextToSpeech
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
    private lateinit var replayButton: Button
    private lateinit var speechModeButton: Button

    private var recognizer: SpeechRecognizer? = null
    private var speechEngine: TextToSpeech? = null
    private val speechStartup = TtsStartupGate()
    private var queuedSpeech: String? = null
    private var lastAnswer: String? = null
    private var orbAnimator: ObjectAnimator? = null
    private var submitted = false
    private val retryPolicy = VoiceRetryPolicy(MAX_AUTOMATIC_RETRIES)
    private val audioPermissionSession = NativeAudioPermissionRequestSession(REQUEST_AUDIO)
    private val screenAwakeSession = NativeVoiceAwakeSession()
    private var currentVoiceState = "idle"
    private val screenAwakeDeadline = Runnable { syncScreenAwake() }
    private val retryListeningRunnable = Runnable {
        if (!submitted && !isFinishing && !isDestroyed) {
            startListening()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Only the initial interactive dictation phase may keep the screen awake,
        // and never longer than the existing monotonic 20-second screen budget.
        screenAwakeSession.startIfAbsent(SystemClock.elapsedRealtime())
        setContentView(buildUi())
        setState("starting", "Klaarmaken…")

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        } else if (audioPermissionSession.beginRequest()) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (audioPermissionSession.onResult(requestCode, permissions.toList(), grantResults.toList())) {
            NativeAudioPermissionResultPolicy.Action.IGNORE_UNRELATED_REQUEST -> Unit
            NativeAudioPermissionResultPolicy.Action.START_LISTENING -> {
                if (!isFinishing && !isDestroyed) startListening()
            }
            NativeAudioPermissionResultPolicy.Action.SHOW_PERMISSION_REQUIRED ->
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
        column.addView(detailText, fullWidth(bottom = 8))

        val audioControls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        speechModeButton = Button(this).apply {
            text = spokenModeLabel(ResponseModeStore.load(this@NativeVoiceActivity))
            textSize = 11f
            isAllCaps = false
            setOnClickListener {
                val next = ResponseModeStore.cycle(this@NativeVoiceActivity)
                text = spokenModeLabel(next)
                if (next == ResponseMode.SILENT) {
                    queuedSpeech = null
                    speechEngine?.stop()
                }
            }
        }
        audioControls.addView(
            speechModeButton,
            LinearLayout.LayoutParams(0, dp(44), 1f)
        )
        replayButton = Button(this).apply {
            text = "↻ Luister"
            textSize = 11f
            isAllCaps = false
            visibility = View.GONE
            setOnClickListener { lastAnswer?.let(::speakText) }
        }
        audioControls.addView(
            replayButton,
            LinearLayout.LayoutParams(0, dp(44), 1f)
        )
        column.addView(audioControls, fullWidth(bottom = 8))

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
            // Some engines return a blank first hypothesis followed by usable speech.
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
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
        val scale = NativeMicLevelScalePolicy.scale(rmsdB)
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

        if (retryable && retryPolicy.tryConsumeRetry()) {
            transcriptText.text = "Ik hoorde niets — nog één keer"
            mainHandler.removeCallbacks(retryListeningRunnable)
            mainHandler.postDelayed(retryListeningRunnable, RETRY_DELAY_MS)
        } else if (retryable) {
            showError("Ik hoor niets")
            detailText.text =
                "Automatisch opnieuw luisteren is gestopt om de microfoon niet actief te houden."
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
        NativeSpeechCandidatePolicy.select(
            bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        )

    private fun submit(text: String) {
        if (submitted) return
        submitted = true
        mainHandler.removeCallbacks(retryListeningRunnable)
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
        val prewarmMode = ResponseModeStore.load(this)
        // Prepare TTS while the HTTPS gateway request is running. This is only a hint;
        // the user may switch audio mode before the reply reaches the UI.
        if (prewarmMode != ResponseMode.SILENT) ensureSpeechEngine()
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
                        lastAnswer = response.answer
                        replayButton.visibility =
                            if (response.answer.isNullOrBlank()) View.GONE else View.VISIBLE

                        // Honor the *current* Watch selection, not the mode when Send was tapped.
                        // In particular, muting while the VPS is answering must never auto-speak.
                        SpokenReplyPolicy.textFor(
                            ResponseModeStore.load(this@NativeVoiceActivity),
                            response.answer
                        )?.let(::speakText)
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
                        // Exception messages may embed private gateway URLs, headers or secrets.
                        // Surface only the reviewed bounded, category-based response.
                        val feedback = NativeVoiceFailureFeedbackPolicy.describe(error)
                        showError(feedback.title)
                        detailText.text = feedback.detail
                    }
                }
        }
    }

    private fun spokenModeLabel(mode: ResponseMode): String = when (mode) {
        ResponseMode.SILENT -> "🔇 Stil"
        ResponseMode.SHORT_SPOKEN -> "🔊 Kort"
        ResponseMode.FULL_SPOKEN -> "🔊 Alles"
    }

    private fun speakText(text: String) {
        if (isFinishing || isDestroyed) return
        val limit = (TextToSpeech.getMaxSpeechInputLength() - 32).coerceAtLeast(200)
        val speech = text.trim().take(limit)
        if (speech.isBlank()) return

        queuedSpeech = speech
        if (speechStartup.isReady()) speakQueued() else ensureSpeechEngine()
    }

    private fun ensureSpeechEngine() {
        if (isFinishing || isDestroyed) return
        val ticket = speechStartup.begin() ?: return

        try {
            speechEngine = TextToSpeech(applicationContext) { status ->
                mainHandler.post {
                    if (status != TextToSpeech.SUCCESS) {
                        if (speechStartup.complete(ticket, false)) onSpeechUnavailable()
                        return@post
                    }

                    val language = runCatching {
                        speechEngine?.setLanguage(Locale.forLanguageTag("nl-NL"))
                            ?: TextToSpeech.ERROR
                    }.getOrDefault(TextToSpeech.ERROR)

                    if (language < 0) {
                        if (speechStartup.complete(ticket, false)) onSpeechUnavailable()
                        return@post
                    }

                    if (speechStartup.complete(ticket, true)) speakQueued()
                }
            }
        } catch (_: RuntimeException) {
            if (speechStartup.complete(ticket, false)) onSpeechUnavailable()
        }
    }

    private fun onSpeechUnavailable() {
        queuedSpeech = null
        releaseSpeechEngine()
        // The answer stays visible; an explicit Replay retries the Android TTS engine.
    }

    private fun releaseSpeechEngine() {
        val engine = speechEngine
        speechEngine = null
        runCatching { engine?.stop() }
        runCatching { engine?.shutdown() }
    }

    private fun speakQueued() {
        val text = queuedSpeech ?: return
        queuedSpeech = null
        val status = runCatching {
            speechEngine?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "raiseai-answer")
                ?: TextToSpeech.ERROR
        }.getOrDefault(TextToSpeech.ERROR)

        if (status == TextToSpeech.ERROR && speechStartup.invalidateReady()) {
            releaseSpeechEngine()
        }
    }

    private fun setState(state: String, label: String) {
        NativeSessionState.set(state)
        currentVoiceState = state
        statusText.text = label
        syncScreenAwake()

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
        currentVoiceState = "error"
        syncScreenAwake()
        submitted = true
        mainHandler.removeCallbacks(retryListeningRunnable)
        recognizer?.cancel()
        NativeSessionState.set("error")
        statusText.text = message
        orbAnimator?.cancel()
        fallbackButton.visibility = View.VISIBLE
    }

    private fun syncScreenAwake() {
        mainHandler.removeCallbacks(screenAwakeDeadline)
        val remaining = screenAwakeSession.remainingMs(
            currentVoiceState, SystemClock.elapsedRealtime()
        )
        if (remaining > 0L && !isFinishing && !isDestroyed) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            mainHandler.postDelayed(screenAwakeDeadline, remaining)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            if (currentVoiceState != "starting" && currentVoiceState != "listening" &&
                currentVoiceState != "understanding"
            ) screenAwakeSession.finish()
        }
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
        mainHandler.removeCallbacksAndMessages(null)
        audioPermissionSession.invalidate()
        screenAwakeSession.invalidate()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        orbAnimator?.cancel()
        recognizer?.cancel()
        recognizer?.destroy()
        queuedSpeech = null
        speechStartup.close()
        releaseSpeechEngine()
        io.shutdownNow()
        NativeSessionState.set("idle")
        super.onDestroy()
    }

    companion object {
        private const val REQUEST_AUDIO = 201
        private const val MAX_AUTOMATIC_RETRIES = 1
        private const val RETRY_DELAY_MS = 700L
    }
}