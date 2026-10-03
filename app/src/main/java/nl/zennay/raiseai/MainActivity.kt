package nl.zennay.raiseai

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kotlin.math.roundToInt

class MainActivity : Activity(), SensorEventListener {
    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private val handler = Handler(Looper.getMainLooper())

    private lateinit var statusText: TextView
    private lateinit var statsText: TextView
    private lateinit var monitorButton: Button
    private lateinit var calibrateButton: Button
    private val captureButtons = mutableListOf<Button>()

    private var calibrationCapturing = false
    private val calibrationSamples = mutableListOf<FloatArray>()

    private var traceLabel: String? = null
    private var traceSessionId = 0L
    private var traceStartedMs = 0L
    private val finishTraceRunnable = Runnable { finishTraceCapture() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)

        setContentView(buildUi())
        requestNotificationPermissionIfNeeded()

        if (intent.getBooleanExtra(EXTRA_OPEN_CHATGPT_LOGIN, false)) {
            handler.post {
                startActivity(
                    Intent(this, ChatGptActivity::class.java)
                        .putExtra(ChatGptActivity.EXTRA_TRY_WEBSITE_MIC, false)
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshUi()
    }

    override fun onPause() {
        if (traceLabel != null) finishTraceCapture(showToast = false)
        if (calibrationCapturing) cancelCalibration()
        sensorManager.unregisterListener(this)
        super.onPause()
    }

    private fun buildUi(): ScrollView {
        val scroll = ScrollView(this).apply {
            setBackgroundColor(Color.BLACK)
            isFillViewport = true
        }
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = android.view.Gravity.CENTER_HORIZONTAL
            setPadding(dp(20), dp(30), dp(20), dp(30))
        }

        column.addView(TextView(this).apply {
            text = "Raise AI"
            setTextColor(Color.WHITE)
            textSize = 24f
            gravity = android.view.Gravity.CENTER
        }, matchWrap())

        column.addView(TextView(this).apply {
            text = "Watch 7 · v1.5.0"
            setTextColor(Color.LTGRAY)
            textSize = 13f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(top = 2, bottom = 12))

        statusText = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 14f
            gravity = android.view.Gravity.CENTER
        }
        column.addView(statusText, matchWrap(bottom = 8))

        statsText = TextView(this).apply {
            setTextColor(Color.LTGRAY)
            textSize = 11f
            gravity = android.view.Gravity.CENTER
        }
        column.addView(statsText, matchWrap(bottom = 12))

        monitorButton = button("Enable raise-to-talk") {
            if (CalibrationStore.isMonitoringEnabled(this)) stopMonitoring() else startMonitoring()
        }
        column.addView(monitorButton, matchWrap(bottom = 8))

        calibrateButton = button("Calibrate mouth pose") { startCalibration() }
        column.addView(calibrateButton, matchWrap(bottom = 8))

        column.addView(button(if (CalibrationStore.isSleepDndPauseEnabled(this)) "Sleep/DND pause: ON" else "Sleep/DND pause: OFF") {
            val next = !CalibrationStore.isSleepDndPauseEnabled(this)
            CalibrationStore.setSleepDndPauseEnabled(this, next)
            if (CalibrationStore.isMonitoringEnabled(this)) {
                stopService(Intent(this, GestureMonitorService::class.java))
                startForegroundService(Intent(this, GestureMonitorService::class.java))
            }
            toast(if (next) "Sleep/DND pause enabled" else "Sleep/DND pause disabled")
            recreate()
        }, matchWrap(bottom = 8))

        column.addView(TextView(this).apply {
            text = "Native Raise AI · VPS routed"
            setTextColor(Color.WHITE)
            textSize = 13f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(top = 2, bottom = 6))

        column.addView(button("Open native Raise AI") {
            if (!NativeVoiceLauncher.launchFromActivity(this)) {
                toast("Native Raise AI could not be opened")
            }
        }, matchWrap(bottom = 6))

        column.addView(TextView(this).apply {
            text = if (GatewayConfig.isConfigured(this@MainActivity)) {
                "✓ Secure VPS gateway configured"
            } else {
                "○ VPS gateway not configured yet"
            }
            setTextColor(Color.LTGRAY)
            textSize = 11f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(bottom = 6))

        column.addView(button("Open ChatGPT Web fallback") {
            if (!ChatGptLauncher.launchFromActivity(this)) {
                toast("ChatGPT fallback could not be opened")
            }
        }, matchWrap(bottom = 12))

        column.addView(TextView(this).apply {
            text = "Gemini + Google Home fallback"
            setTextColor(Color.WHITE)
            textSize = 13f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(bottom = 6))

        column.addView(button("Test Gemini voice") {
            val result = AssistantLauncher.launchFromActivity(this)
            if (!result.success) toast("Google/Gemini could not be opened")
        }, matchWrap(bottom = 6))

        column.addView(button("Test AI question") {
            toast("Ask Gemini any normal AI question")
            AssistantLauncher.launchFromActivity(this)
        }, matchWrap(bottom = 6))

        column.addView(button("Test Google Home command") {
            toast("Tell Gemini to control one of your real Home devices")
            AssistantLauncher.launchFromActivity(this)
        }, matchWrap(bottom = 6))

        column.addView(button("Open Google Home") {
            if (!HomeLauncher.open(this)) toast("Google Home could not be opened")
        }, matchWrap(bottom = 6))

        column.addView(TextView(this).apply {
            text = "For Home control, Gemini on your paired Android phone must use the same personal Google account as Google Home, with Google Home enabled under Gemini's Connected apps."
            setTextColor(Color.LTGRAY)
            textSize = 11f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(bottom = 14))

        column.addView(TextView(this).apply {
            text = "Gesture test data"
            setTextColor(Color.WHITE)
            textSize = 13f
            gravity = android.view.Gravity.CENTER
        }, matchWrap(bottom = 6))

        addCaptureButton(column, "Record mouth raise · 4 sec", "mouth_raise")
        addCaptureButton(column, "Record check-time raise · 4 sec", "view_time")
        addCaptureButton(column, "Record normal movement · 4 sec", "normal_move")

        column.addView(button("Clear recorded samples") {
            SensorTraceRecorder.clear(this)
            CalibrationStore.clearTriggerStats(this)
            toast("Test data cleared")
            refreshUi()
        }, matchWrap(top = 2, bottom = 12))

        column.addView(TextView(this).apply {
            text = "Setup: calibrate once, enable monitoring, then raise your wrist close to your mouth. " +
                "Use the three Record buttons to collect real Watch 7 motion data before tuning the detector."
            setTextColor(Color.LTGRAY)
            textSize = 12f
            gravity = android.view.Gravity.CENTER
        }, matchWrap())

        scroll.addView(column)
        return scroll
    }

    private fun addCaptureButton(column: LinearLayout, label: String, trace: String) {
        val b = button(label) { startTraceCapture(trace) }
        captureButtons += b
        column.addView(b, matchWrap(bottom = 6))
    }

    private fun startMonitoring() {
        if (CalibrationStore.loadPose(this) == null) {
            toast("Calibrate your mouth pose first")
            return
        }
        val intent = Intent(this, GestureMonitorService::class.java)
        startForegroundService(intent)
        CalibrationStore.setMonitoringEnabled(this, true)
        refreshUi()
    }

    private fun stopMonitoring() {
        stopService(Intent(this, GestureMonitorService::class.java))
        CalibrationStore.setMonitoringEnabled(this, false)
        refreshUi()
    }

    private fun startCalibration() {
        if (calibrationCapturing || traceLabel != null) return
        calibrationCapturing = true
        calibrationSamples.clear()
        setCaptureControlsEnabled(false)
        statusText.text = "3… raise the watch toward your mouth"

        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        } ?: run {
            toast("No accelerometer found")
            calibrationCapturing = false
            setCaptureControlsEnabled(true)
            return
        }

        handler.postDelayed({ if (calibrationCapturing) statusText.text = "2…" }, 700)
        handler.postDelayed({ if (calibrationCapturing) statusText.text = "1… hold it at your mouth" }, 1_400)
        handler.postDelayed({
            if (calibrationCapturing) {
                calibrationSamples.clear()
                statusText.text = "Hold…"
            }
        }, 2_000)
        handler.postDelayed({ if (calibrationCapturing) finishCalibration() }, 2_900)
    }

    private fun cancelCalibration() {
        calibrationCapturing = false
        calibrationSamples.clear()
        sensorManager.unregisterListener(this)
        setCaptureControlsEnabled(true)
        refreshUi()
    }

    private fun finishCalibration() {
        sensorManager.unregisterListener(this)
        calibrationCapturing = false
        setCaptureControlsEnabled(true)

        if (calibrationSamples.size < 3) {
            toast("Not enough sensor samples — try again")
            refreshUi()
            return
        }

        val x = calibrationSamples.map { it[0] }.average().toFloat()
        val y = calibrationSamples.map { it[1] }.average().toFloat()
        val z = calibrationSamples.map { it[2] }.average().toFloat()
        CalibrationStore.savePose(this, x, y, z)
        toast("Mouth pose saved")

        if (CalibrationStore.isMonitoringEnabled(this)) {
            stopService(Intent(this, GestureMonitorService::class.java))
            startForegroundService(Intent(this, GestureMonitorService::class.java))
        }
        refreshUi()
    }

    private fun startTraceCapture(label: String) {
        if (calibrationCapturing || traceLabel != null) return
        val sensor = accelerometer ?: run {
            toast("No accelerometer found")
            return
        }

        traceLabel = label
        traceSessionId = System.currentTimeMillis()
        traceStartedMs = SystemClock.elapsedRealtime()
        setCaptureControlsEnabled(false)
        statusText.text = when (label) {
            "mouth_raise" -> "Recording… raise naturally to your mouth"
            "view_time" -> "Recording… check the time naturally"
            else -> "Recording… move your arm normally"
        }

        sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
        handler.removeCallbacks(finishTraceRunnable)
        handler.postDelayed(finishTraceRunnable, TRACE_DURATION_MS)
    }

    private fun finishTraceCapture(showToast: Boolean = true) {
        if (traceLabel == null) return
        handler.removeCallbacks(finishTraceRunnable)
        sensorManager.unregisterListener(this)
        traceLabel = null
        setCaptureControlsEnabled(true)
        if (showToast) toast("Recorded. Total samples: ${SensorTraceRecorder.sampleCount(this)}")
        refreshUi()
    }

    private fun setCaptureControlsEnabled(enabled: Boolean) {
        calibrateButton.isEnabled = enabled
        captureButtons.forEach { it.isEnabled = enabled }
        monitorButton.isEnabled = enabled
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return

        if (calibrationCapturing) {
            calibrationSamples += floatArrayOf(event.values[0], event.values[1], event.values[2])
        }

        val label = traceLabel
        if (label != null) {
            SensorTraceRecorder.append(
                context = this,
                label = label,
                sessionId = traceSessionId,
                elapsedMs = SystemClock.elapsedRealtime() - traceStartedMs,
                x = event.values[0],
                y = event.values[1],
                z = event.values[2]
            )
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    private fun refreshUi() {
        val calibrated = CalibrationStore.loadPose(this) != null
        val enabled = CalibrationStore.isMonitoringEnabled(this)
        statusText.text = buildString {
            append(if (calibrated) "✓ Calibrated" else "○ Needs calibration")
            append("\n")
            append(if (enabled) "● Monitoring on" else "○ Monitoring off")
            append("\n")
            append(if (Settings.canDrawOverlays(this@MainActivity)) "✓ Hands-free Raise AI grant" else "○ Hands-free Raise AI grant missing")
            append("\n")
            append(if (AssistantSessionGuard(this@MainActivity).hasUsageAccess()) "✓ Assistant session guard" else "○ Session guard fallback: 30 sec")
            append("\n")
            append(if (CalibrationStore.isSleepDndPauseEnabled(this@MainActivity)) "✓ Sleep/DND pause" else "○ Sleep/DND pause off")
        }
        monitorButton.text = if (enabled) "Disable raise-to-talk" else "Enable raise-to-talk"

        val triggers = CalibrationStore.triggerCount(this)
        val samples = SensorTraceRecorder.sampleCount(this)
        val lastSimilarity = CalibrationStore.lastTriggerSimilarity(this)
        val assistantPath = CalibrationStore.lastAssistantPath(this)
        val activeMinutes = CalibrationStore.activeMonitoringMs(this) / 60_000L
        val sleepMinutes = CalibrationStore.sleepPausedMs(this) / 60_000L
        val sessionBlocks = CalibrationStore.sessionBlockCount(this)
        statsText.text = buildString {
            append("Triggers: $triggers · Samples: $samples")
            if (triggers > 0) append("\nLast match: ${"%.3f".format(lastSimilarity)}")
            append("\nAssistant route: $assistantPath")
            append("\nActive: ${activeMinutes}m · Sleep paused: ${sleepMinutes}m")
            append("\nAssistant retriggers blocked: $sessionBlocks")
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }

    private fun button(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        textSize = 13f
        isAllCaps = false
        setOnClickListener { action() }
        minHeight = dp(48)
    }

    private fun matchWrap(top: Int = 0, bottom: Int = 0): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = dp(top)
            bottomMargin = dp(bottom)
        }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    companion object {
        const val EXTRA_OPEN_CHATGPT_LOGIN = "open_chatgpt_login"
        private const val TRACE_DURATION_MS = 4_000L
    }
}