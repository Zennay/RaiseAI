package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast

/** Notification-tap fallback only. Gesture launches use AssistantLauncher directly. */
class AssistantProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }

        val result = AssistantLauncher.launchFromActivity(this)
        if (!result.success) {
            Toast.makeText(
                this,
                "Gemini kon niet worden geopend. Controleer de assistentinstellingen in Raise AI.",
                Toast.LENGTH_LONG
            ).show()
            startActivity(
                Intent(this, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                }
            )
        }
        finish()
    }
}
