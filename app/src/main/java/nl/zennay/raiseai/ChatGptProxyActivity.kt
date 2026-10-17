package nl.zennay.raiseai

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast

/** Notification action that opens the bundled RaiseGPT Wear browser. */
class ChatGptProxyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }
        if (ChatGptLauncher.launchFromActivity(this)) {
            finish()
            return
        }

        Toast.makeText(this, "ChatGPT fallback could not be opened", Toast.LENGTH_SHORT).show()
        runCatching {
            startActivity(Intent(this, MainActivity::class.java))
        }
        finish()
    }
}
