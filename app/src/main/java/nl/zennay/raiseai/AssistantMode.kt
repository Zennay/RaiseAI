package nl.zennay.raiseai

import android.app.Activity
import android.content.Context

enum class AssistantMode(
    val storedValue: String,
    val label: String
) {
    GEMINI("gemini", "Gemini"),
    NATIVE("native", "Native Raise AI");

    fun alternate(): AssistantMode =
        when (this) {
            GEMINI -> NATIVE
            NATIVE -> GEMINI
        }
}

object AssistantModeStore {
    private const val PREFS = "raise_ai_prefs"
    private const val KEY_ASSISTANT_MODE = "assistant_mode"

    fun resolve(stored: String?): AssistantMode =
        when (stored) {
            AssistantMode.NATIVE.storedValue -> AssistantMode.NATIVE
            else -> AssistantMode.GEMINI
        }

    internal fun readStoredValue(read: () -> String?): String? =
        try {
            read()
        } catch (_: RuntimeException) {
            null
        }

    fun get(context: Context): AssistantMode {
        val stored = readStoredValue {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(KEY_ASSISTANT_MODE, null)
        }

        return resolve(stored)
    }

    fun set(context: Context, mode: AssistantMode) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_ASSISTANT_MODE, mode.storedValue)
            .apply()
    }
}

object PreferredAssistantLauncher {
    fun launchFromActivity(activity: Activity): Boolean =
        when (AssistantModeStore.get(activity)) {
            AssistantMode.GEMINI -> AssistantLauncher.launchFromActivity(activity).success
            AssistantMode.NATIVE -> NativeVoiceLauncher.launchFromActivity(activity)
        }

    fun launchFromService(context: Context): Boolean =
        when (AssistantModeStore.get(context)) {
            AssistantMode.GEMINI -> AssistantLauncher.launchFromService(context).success
            AssistantMode.NATIVE -> NativeVoiceLauncher.launchFromService(context)
        }
}
