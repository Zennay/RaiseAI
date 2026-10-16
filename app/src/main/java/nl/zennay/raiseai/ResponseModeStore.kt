package nl.zennay.raiseai

import android.content.Context

object ResponseModeStore {
    private const val PREFS = "raise_ai_response_prefs"
    private const val KEY_MODE = "response_mode"

    fun load(context: Context): ResponseMode {
        val stored = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_MODE, null)
        return ResponseMode.fromStored(stored)
    }

    fun set(context: Context, mode: ResponseMode) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_MODE, mode.name)
            .apply()
    }

    fun cycle(context: Context): ResponseMode {
        val next = load(context).next()
        set(context, next)
        return next
    }
}
