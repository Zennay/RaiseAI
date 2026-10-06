package nl.zennay.raiseai

import android.content.Context
import kotlin.math.sqrt

object CalibrationStore {
    private const val PREFS = "raise_ai_prefs"
    private const val KEY_X = "mouth_x"
    private const val KEY_Y = "mouth_y"
    private const val KEY_Z = "mouth_z"
    private const val KEY_CALIBRATED = "calibrated"
    private const val KEY_ENABLED = "monitoring_enabled"
    private const val KEY_SLEEP_DND_PAUSE = "sleep_dnd_pause"
    private const val KEY_TRIGGER_COUNT = "trigger_count"
    private const val KEY_LAST_TRIGGER_AT = "last_trigger_at"
    private const val KEY_LAST_SIMILARITY = "last_similarity"
    private const val KEY_LAST_ASSISTANT_PATH = "last_assistant_path"
    private const val KEY_LAST_ASSISTANT_AT = "last_assistant_at"
    private const val KEY_ACTIVE_MS = "active_monitor_ms"
    private const val KEY_SLEEP_PAUSED_MS = "sleep_paused_ms"
    private const val KEY_SENSOR_EVENTS = "sensor_events"
    private const val KEY_SESSION_BLOCKS = "assistant_session_blocks"

    fun savePose(context: Context, x: Float, y: Float, z: Float) {
        val normalized = normalize(x, y, z) ?: return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putFloat(KEY_X, normalized.x)
            .putFloat(KEY_Y, normalized.y)
            .putFloat(KEY_Z, normalized.z)
            .putBoolean(KEY_CALIBRATED, true)
            .apply()
    }

    fun loadPose(context: Context): MouthPose? {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (!p.getBoolean(KEY_CALIBRATED, false)) return null
        return MouthPose(
            p.getFloat(KEY_X, 0f),
            p.getFloat(KEY_Y, 0f),
            p.getFloat(KEY_Z, 0f)
        )
    }

    fun setMonitoringEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ENABLED, enabled)
            .apply()
    }

    fun isMonitoringEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_ENABLED, false)

    fun setSleepDndPauseEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_SLEEP_DND_PAUSE, enabled)
            .apply()
    }

    fun isSleepDndPauseEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_SLEEP_DND_PAUSE, true)

    fun recordTrigger(context: Context, similarity: Float) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit()
            .putInt(
                KEY_TRIGGER_COUNT,
                CounterMath.incrementNonNegative(prefs.getInt(KEY_TRIGGER_COUNT, 0))
            )
            .putLong(KEY_LAST_TRIGGER_AT, System.currentTimeMillis())
            .putFloat(KEY_LAST_SIMILARITY, similarity)
            .apply()
    }

    fun triggerCount(context: Context): Int =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getInt(KEY_TRIGGER_COUNT, 0)

    fun lastTriggerAt(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getLong(KEY_LAST_TRIGGER_AT, 0L)

    fun lastTriggerSimilarity(context: Context): Float =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getFloat(KEY_LAST_SIMILARITY, 0f)

    fun recordAssistantLaunch(context: Context, path: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LAST_ASSISTANT_PATH, path)
            .putLong(KEY_LAST_ASSISTANT_AT, System.currentTimeMillis())
            .apply()
    }

    fun lastAssistantPath(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_LAST_ASSISTANT_PATH, "not tested") ?: "not tested"

    fun lastAssistantAt(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getLong(KEY_LAST_ASSISTANT_AT, 0L)

    @Synchronized
    fun addRuntimeStats(
        context: Context,
        activeMs: Long,
        sleepPausedMs: Long,
        sensorEvents: Long,
        sessionBlocks: Long
    ) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit()
            .putLong(
                KEY_ACTIVE_MS,
                CounterMath.addNonNegative(prefs.getLong(KEY_ACTIVE_MS, 0L), activeMs)
            )
            .putLong(
                KEY_SLEEP_PAUSED_MS,
                CounterMath.addNonNegative(prefs.getLong(KEY_SLEEP_PAUSED_MS, 0L), sleepPausedMs)
            )
            .putLong(
                KEY_SENSOR_EVENTS,
                CounterMath.addNonNegative(prefs.getLong(KEY_SENSOR_EVENTS, 0L), sensorEvents)
            )
            .putLong(
                KEY_SESSION_BLOCKS,
                CounterMath.addNonNegative(prefs.getLong(KEY_SESSION_BLOCKS, 0L), sessionBlocks)
            )
            .apply()
    }

    fun activeMonitoringMs(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_ACTIVE_MS, 0L)

    fun sleepPausedMs(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_SLEEP_PAUSED_MS, 0L)

    fun sensorEventCount(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_SENSOR_EVENTS, 0L)

    fun sessionBlockCount(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_SESSION_BLOCKS, 0L)

    fun clearTriggerStats(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_TRIGGER_COUNT)
            .remove(KEY_LAST_TRIGGER_AT)
            .remove(KEY_LAST_SIMILARITY)
            .remove(KEY_ACTIVE_MS)
            .remove(KEY_SLEEP_PAUSED_MS)
            .remove(KEY_SENSOR_EVENTS)
            .remove(KEY_SESSION_BLOCKS)
            .apply()
    }

    private fun normalize(x: Float, y: Float, z: Float): MouthPose? {
        val length = sqrt(x * x + y * y + z * z)
        if (length < 0.001f) return null
        return MouthPose(x / length, y / length, z / length)
    }
}
