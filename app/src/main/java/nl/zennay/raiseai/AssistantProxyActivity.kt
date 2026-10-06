package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/** Notification-tap fallback only. Gesture launches use AssistantLauncher directly. */
class AssistantProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }

        val launched = AssistantLauncher.launchFromActivity(this)
        if (!launched.success) {
            openSetup()
        }
        finish()
    }

    private fun openSetup() {
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        )
    }
}
