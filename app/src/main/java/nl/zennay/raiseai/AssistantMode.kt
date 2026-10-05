package nl.zennay.raiseai

import android.app.Activity
import android.content.Context

enum class AssistantMode(
    val storedValue: String,
    val label: String
) {
    GEMINI("gemini", "Gemini"),
    NATIVE("native", "Native Raise AI"),
    CHATGPT("chatgpt", "ChatGPT");

    fun next(): AssistantMode =
        when (this) {
            GEMINI -> NATIVE
            NATIVE -> CHATGPT
            CHATGPT -> GEMINI
        }
}

object AssistantModeStore {
    private const val PREFS = "raise_ai_prefs"
    private const val KEY_ASSISTANT_MODE = "assistant_mode"
    private const val KEY_ASSISTANT_MODE_SCHEMA = "assistant_mode_schema"
    internal const val CURRENT_MODE_SCHEMA = 1

    fun resolve(stored: String?): AssistantMode =
        when (stored) {
            AssistantMode.NATIVE.storedValue -> AssistantMode.NATIVE
            AssistantMode.CHATGPT.storedValue -> AssistantMode.CHATGPT
            else -> AssistantMode.GEMINI
        }

    fun resolve(stored: String?, schemaVersion: Int): AssistantMode =
        if (schemaVersion < CURRENT_MODE_SCHEMA) {
            AssistantMode.GEMINI
        } else {
            resolve(stored)
        }

    fun get(context: Context): AssistantMode {
        val preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = preferences.getString(KEY_ASSISTANT_MODE, null)
        val schemaVersion = preferences.getInt(KEY_ASSISTANT_MODE_SCHEMA, 0)
        val resolved = resolve(stored, schemaVersion)

        if (schemaVersion < CURRENT_MODE_SCHEMA) {
            preferences.edit()
                .putString(KEY_ASSISTANT_MODE, resolved.storedValue)
                .putInt(KEY_ASSISTANT_MODE_SCHEMA, CURRENT_MODE_SCHEMA)
                .apply()
        }

        return resolved
    }

    fun set(context: Context, mode: AssistantMode) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_ASSISTANT_MODE, mode.storedValue)
            .putInt(KEY_ASSISTANT_MODE_SCHEMA, CURRENT_MODE_SCHEMA)
            .apply()
    }
}

object PreferredAssistantLauncher {
    fun launchFromActivity(activity: Activity): Boolean =
        when (AssistantModeStore.get(activity)) {
            AssistantMode.GEMINI -> AssistantLauncher.launchFromActivity(activity).success
            AssistantMode.NATIVE -> NativeVoiceLauncher.launchFromActivity(activity)
            AssistantMode.CHATGPT -> ChatGptLauncher.launchFromActivity(activity)
        }

    fun launchFromService(context: Context): Boolean =
        when (AssistantModeStore.get(context)) {
            AssistantMode.GEMINI -> AssistantLauncher.launchFromService(context).success
            AssistantMode.NATIVE -> NativeVoiceLauncher.launchFromService(context)
            AssistantMode.CHATGPT -> ChatGptLauncher.launchFromService(context)
        }
}
