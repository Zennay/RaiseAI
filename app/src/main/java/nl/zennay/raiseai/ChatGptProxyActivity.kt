package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/** Notification action that opens the bundled RaiseGPT Wear browser. */
class ChatGptProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }

        if (!ChatGptLauncher.launchFromActivity(this)) {
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
