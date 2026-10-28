package nl.zennay.raiseai.phone

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Explicit and visible operator control: no background starts, no ChatGPT account credentials,
 * and no unsupported Voice/Watch audio routing.
 */
class PhoneCompanionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 40, 32, 40)
        }
        root.addView(container)

        fun note(message: String, fontSize: Float = 16f): TextView =
            TextView(this).also {
                it.text = message
                it.textSize = fontSize
                it.setTextColor(Color.DKGRAY)
                it.setPadding(0, 0, 0, 24)
                container.addView(it)
            }

        note("Raise AI · official ChatGPT phone launch", 22f)
        note("This development companion can only open the installed official ChatGPT app. " +
            "It does not open Voice automatically or route Watch microphone or speaker audio.")
        note("Get the signing certificate SHA-256 from a separately authenticated, trustworthy " +
            "publisher reference. Do NOT copy it from the installed APK: a matching attacker " +
            "certificate would prove nothing.")
        val fingerprint = EditText(this).apply {
            hint = "Official publisher cert SHA-256 (64 hex)"
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        container.addView(fingerprint, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        val status = note("No account details, API keys, cookies or audio are collected.")
        val button = Button(this).apply {
            text = "Verify signature and open ChatGPT"
            gravity = Gravity.CENTER
            setOnClickListener {
                // Never save or transmit a fingerprint; checked on each explicit button tap.
                val result = OfficialChatGptLauncher(this@PhoneCompanionActivity)
                    .launchOnExplicitButtonTap(fingerprint.text.toString().trim())
                status.text = when (result) {
                    OfficialChatGptLauncher.Result.OPENED_OFFICIAL_APP ->
                        "Official package signature matches your reference. " +
                        "ChatGPT opened; manually tap Voice within the official app."
                    OfficialChatGptLauncher.Result.MISSING_APP ->
                        "ChatGPT Android app not installed. Install from a trusted app store."
                    OfficialChatGptLauncher.Result.SIGNER_MISMATCH_OR_UNVERIFIED ->
                        "Signature missing, unverified, or mismatched. No app opened."
                    OfficialChatGptLauncher.Result.LAUNCHER_UNAVAILABLE ->
                        "Official app launcher unavailable. No Voice mode was requested."
                    OfficialChatGptLauncher.Result.LAUNCH_FAILED ->
                        "Android blocked the public app launch. Reopen this companion and retry."
                }
            }
        }
        container.addView(button)
        setContentView(root)
    }
}
