package nl.zennay.raiseai

import android.app.Activity
import android.os.Bundle

/** Notification action that opens the bundled RaiseGPT Wear browser. */
class ChatGptProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }
        ChatGptLauncher.launchFromActivity(this)
        finish()
    }
}
