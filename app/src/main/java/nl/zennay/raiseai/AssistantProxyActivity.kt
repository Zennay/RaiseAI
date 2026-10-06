package nl.zennay.raiseai

import android.app.Activity
import android.os.Bundle

/** Notification-tap fallback only. Gesture launches use AssistantLauncher directly. */
class AssistantProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }
        AssistantLauncher.launchFromActivity(this)
        finish()
    }
}
