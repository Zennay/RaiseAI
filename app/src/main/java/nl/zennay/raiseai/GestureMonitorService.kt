package nl.zennay.raiseai

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log

class GestureMonitorService : Service(), SensorEventListener {
    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private val detector = RaiseGestureDetector()
    private var mouthPose: MouthPose? = null
    private lateinit var sessionGuard: AssistantSessionGuard
    private val handler = Handler(Looper.getMainLooper())

    private var sensorRegistered = false
    private var sleepPaused = false
    private var stateSinceElapsedMs = 0L
    private var activeMsPending = 0L
    private var sleepPausedMsPending = 0L
    private var sensorEventsPending = 0L
    private var sessionBlocksPending = 0L

    private val powerStateRunnable = object : Runnable {
        override fun run() {
            applyPowerState()
            handler.postDelayed(this, POWER_STATE_CHECK_MS)
        }
    }

    private val statsFlushRunnable = object : Runnable {
        override fun run() {
            flushRuntimeStats()
            handler.postDelayed(this, STATS_FLUSH_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        startAsForeground()

        mouthPose = CalibrationStore.loadPose(this)
        sessionGuard = AssistantSessionGuard(this)
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        stateSinceElapsedMs = SystemClock.elapsedRealtime()

        if (accelerometer == null) {
            Log.e(TAG, "No accelerometer found; stopping service")
            stopSelf()
            return
        }

        CalibrationStore.setMonitoringEnabled(this, true)
        applyPowerState(force = true)

        handler.postDelayed(powerStateRunnable, POWER_STATE_CHECK_MS)
        handler.postDelayed(statsFlushRunnable, STATS_FLUSH_MS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            CalibrationStore.setMonitoringEnabled(this, false)
            stopSelf()
            return START_NOT_STICKY
        }
        mouthPose = CalibrationStore.loadPose(this)
        applyPowerState()
        return START_STICKY
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return
        sensorEventsPending++

        // Sensor timestamps are monotonic nanoseconds since boot and remain correct even when
        // events are delivered in a batch. Using them keeps hold/cooldown timing reliable.
        val eventTimeMs = event.timestamp / 1_000_000L
        val result = detector.onAccelerometer(
            event.values[0],
            event.values[1],
            event.values[2],
            eventTimeMs,
            mouthPose
        )

        if (!result.triggered) return

        if (sessionGuard.shouldBlockLaunch()) {
            sessionBlocksPending++
            updateNotification("Raise AI is already active · waiting for a fresh raise")
            Log.i(TAG, "Blocked retrigger because an assistant session is active")
            return
        }

        Log.i(TAG, "Raise detected similarity=${result.similarity}")
        CalibrationStore.recordTrigger(this, result.similarity)
        vibrate()
        val launched = PreferredAssistantLauncher.launchFromService(this)
        if (launched) {
            sessionGuard.markAssistantLaunched()
            updateNotification("Raise AI listening · lower wrist before the next raise")
        } else {
            updateNotification("Gesture detected · open Raise AI to repair assistant launch")
            Log.w(TAG, "Preferred assistant launch blocked")
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun onDestroy() {
        handler.removeCallbacks(powerStateRunnable)
        handler.removeCallbacks(statsFlushRunnable)
        unregisterAccelerometer()
        flushRuntimeStats()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun applyPowerState(force: Boolean = false) {
        val shouldPauseForSleep = CalibrationStore.isSleepDndPauseEnabled(this) &&
            SleepModePolicy.isSleepOrDndActive(this)

        if (!force && shouldPauseForSleep == sleepPaused) return
        transitionRuntimeState(shouldPauseForSleep)
        sleepPaused = shouldPauseForSleep

        if (sleepPaused) {
            unregisterAccelerometer()
            updateNotification("Paused for Sleep / Do Not Disturb")
        } else {
            registerAccelerometer()
            updateNotification("Raise your watch to your mouth for Raise AI")
        }
    }

    private fun registerAccelerometer() {
        if (sensorRegistered) return
        val sensor = accelerometer ?: return

        // ~10 Hz is enough for the current 180 ms hold detector. A small FIFO latency allows
        // hardware batching on devices that support it, reducing application-processor wakeups.
        val batchLatencyUs = if (sensor.fifoMaxEventCount > 0) SENSOR_BATCH_LATENCY_US else 0
        sensorRegistered = sensorManager.registerListener(
            this,
            sensor,
            SENSOR_SAMPLING_US,
            batchLatencyUs
        )
        Log.i(TAG, "Accelerometer registered; batching=${batchLatencyUs > 0}")
    }

    private fun unregisterAccelerometer() {
        if (!sensorRegistered) return
        sensorManager.unregisterListener(this)
        sensorRegistered = false
        Log.i(TAG, "Accelerometer paused")
    }

    private fun transitionRuntimeState(nextPaused: Boolean) {
        val now = SystemClock.elapsedRealtime()
        if (stateSinceElapsedMs != 0L) {
            val delta = (now - stateSinceElapsedMs).coerceAtLeast(0L)
            if (sleepPaused) sleepPausedMsPending += delta else activeMsPending += delta
        }
        stateSinceElapsedMs = now
        sleepPaused = nextPaused
    }

    private fun flushRuntimeStats() {
        val now = SystemClock.elapsedRealtime()
        if (stateSinceElapsedMs != 0L) {
            val delta = (now - stateSinceElapsedMs).coerceAtLeast(0L)
            if (sleepPaused) sleepPausedMsPending += delta else activeMsPending += delta
            stateSinceElapsedMs = now
        }

        if (activeMsPending == 0L && sleepPausedMsPending == 0L &&
            sensorEventsPending == 0L && sessionBlocksPending == 0L
        ) return

        CalibrationStore.addRuntimeStats(
            this,
            activeMs = activeMsPending,
            sleepPausedMs = sleepPausedMsPending,
            sensorEvents = sensorEventsPending,
            sessionBlocks = sessionBlocksPending
        )
        activeMsPending = 0L
        sleepPausedMsPending = 0L
        sensorEventsPending = 0L
        sessionBlocksPending = 0L
    }

    private fun startAsForeground() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Raise-to-talk",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Keeps raise-to-mouth gesture detection active"
        }
        manager.createNotificationChannel(channel)

        val notification = buildNotification("Raise your watch to your mouth for Raise AI")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(status: String): Notification {
        val openPending = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stopPending = PendingIntent.getService(
            this,
            2,
            Intent(this, GestureMonitorService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val selectedAssistant = AssistantModeStore.get(this)
        val alternateAssistant = selectedAssistant.next()
        val preferredAssistantIntent = when (selectedAssistant) {
            AssistantMode.GEMINI -> Intent(this, AssistantProxyActivity::class.java)
            AssistantMode.NATIVE -> Intent(this, NativeVoiceActivity::class.java)
            AssistantMode.CHATGPT -> Intent(this, ChatGptActivity::class.java)
                .putExtra(ChatGptActivity.EXTRA_TRY_WEBSITE_MIC, true)
        }
        val talkPending = PendingIntent.getActivity(
            this,
            3,
            preferredAssistantIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val alternateAssistantIntent = when (alternateAssistant) {
            AssistantMode.GEMINI -> Intent(this, AssistantProxyActivity::class.java)
            AssistantMode.NATIVE -> Intent(this, NativeVoiceActivity::class.java)
            AssistantMode.CHATGPT -> Intent(this, ChatGptActivity::class.java)
                .putExtra(ChatGptActivity.EXTRA_TRY_WEBSITE_MIC, true)
        }
        val alternatePending = PendingIntent.getActivity(
            this,
            4,
            alternateAssistantIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_raise_ai)
            .setContentTitle("Raise AI is ready")
            .setContentText(status)
            .setOngoing(true)
            .setContentIntent(openPending)
            .addAction(Notification.Action.Builder(null, selectedAssistant.label, talkPending).build())
            .addAction(Notification.Action.Builder(null, alternateAssistant.label, alternatePending).build())
            .addAction(Notification.Action.Builder(null, "Stop", stopPending).build())
            .build()
    }

    private fun updateNotification(status: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(status))
    }

    private fun vibrate() {
        val vibrator: Vibrator = if (Build.VERSION.SDK_INT >= 31) {
            getSystemService(VibratorManager::class.java).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }
        vibrator.vibrate(VibrationEffect.createOneShot(35L, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    companion object {
        private const val TAG = "RaiseAI.Gesture"
        private const val CHANNEL_ID = "raise_ai_monitor"
        private const val NOTIFICATION_ID = 701
        private const val SENSOR_SAMPLING_US = 100_000 // ~10 Hz
        private const val SENSOR_BATCH_LATENCY_US = 250_000
        private const val POWER_STATE_CHECK_MS = 60_000L
        private const val STATS_FLUSH_MS = 15L * 60L * 1_000L
        const val ACTION_STOP = "nl.zennay.raiseai.STOP_MONITORING"
    }
}