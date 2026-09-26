package nl.zennay.raiseai

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import org.mozilla.geckoview.GeckoResult
import org.mozilla.geckoview.GeckoRuntime
import org.mozilla.geckoview.GeckoSession
import org.mozilla.geckoview.GeckoView
import kotlin.math.roundToInt

/**
 * Wear-sized shell around the official ChatGPT website, rendered by bundled GeckoView.
 *
 * A built-in WebExtension only changes presentation and forwards taps to the website's own
 * microphone/send controls. It never reads conversations, exports cookies or calls private APIs.
 */
class ChatGptActivity : Activity() {
    private lateinit var geckoView: GeckoView
    private lateinit var session: GeckoSession
    private lateinit var statusPill: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var canGoBack = false
    private var pendingAndroidPermission: GeckoSession.PermissionDelegate.Callback? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(buildUi())
        ensureMicrophonePermission()

        runCatching { startGecko() }.onFailure {
            showStatus("Wear-browser kon niet starten · Samsung Internet openen…")
            handler.postDelayed({
                runCatching { startActivity(ChatGptLauncher.browserFallbackIntent(this)) }
                finish()
            }, 1_200L)
        }
    }

    private fun buildUi(): FrameLayout {
        geckoView = GeckoView(this).apply {
            setBackgroundColor(Color.BLACK)
            overScrollMode = View.OVER_SCROLL_NEVER
        }
        statusPill = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(235, 28, 28, 31))
            textSize = 11f
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(6), dp(12), dp(6))
        }
        return FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(geckoView, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            ))
            addView(statusPill, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP or Gravity.CENTER_HORIZONTAL
            ).apply {
                topMargin = dp(9)
                marginStart = dp(38)
                marginEnd = dp(38)
            })
        }
    }

    private fun startGecko() {
        showStatus("RaiseGPT starten…")
        val runtime = GeckoEngine.runtime(this)
        session = GeckoSession().apply {
            permissionDelegate = permissionDelegate()
            navigationDelegate = object : GeckoSession.NavigationDelegate {
                override fun onCanGoBack(session: GeckoSession, value: Boolean) {
                    canGoBack = value
                }
            }
            progressDelegate = object : GeckoSession.ProgressDelegate {
                override fun onPageStart(session: GeckoSession, url: String) {
                    showStatus(if (isTrustedChatGptOrigin(url)) "ChatGPT laden…" else "Veilig inloggen…")
                }

                override fun onPageStop(session: GeckoSession, success: Boolean) {
                    if (success) showStatus("Klaar · tik de grote microfoon", 2_200L)
                    else showStatus("Laden mislukt · controleer wifi", 5_000L)
                }
            }
        }
        session.open(runtime)
        geckoView.setSession(session)

        runtime.webExtensionController.ensureBuiltIn(EXTENSION_URI, EXTENSION_ID).accept(
            { session.loadUri(CHATGPT_URL) },
            {
                showStatus("Wear UI kon niet laden · opnieuw proberen", 5_000L)
                session.loadUri(CHATGPT_URL)
            }
        )
    }

    private fun permissionDelegate() = object : GeckoSession.PermissionDelegate {
        override fun onAndroidPermissionsRequest(
            session: GeckoSession,
            permissions: Array<out String>?,
            callback: GeckoSession.PermissionDelegate.Callback
        ) {
            val requested = permissions.orEmpty()
            val audioOnly = requested.isNotEmpty() && requested.all {
                it == Manifest.permission.RECORD_AUDIO
            }
            if (!audioOnly) {
                callback.reject()
            } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                callback.grant()
            } else {
                pendingAndroidPermission?.reject()
                pendingAndroidPermission = callback
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MICROPHONE)
            }
        }

        override fun onContentPermissionRequest(
            session: GeckoSession,
            permission: GeckoSession.PermissionDelegate.ContentPermission
        ): GeckoResult<Int> {
            val trusted = isTrustedChatGptOrigin(permission.uri)
            val allowedType = permission.permission ==
                GeckoSession.PermissionDelegate.PERMISSION_PERSISTENT_STORAGE ||
                permission.permission == GeckoSession.PermissionDelegate.PERMISSION_AUTOPLAY_INAUDIBLE
            return GeckoResult.fromValue(
                if (trusted && allowedType) GeckoSession.PermissionDelegate.ContentPermission.VALUE_ALLOW
                else GeckoSession.PermissionDelegate.ContentPermission.VALUE_DENY
            )
        }

        override fun onMediaPermissionRequest(
            session: GeckoSession,
            uri: String,
            video: Array<out GeckoSession.PermissionDelegate.MediaSource>?,
            audio: Array<out GeckoSession.PermissionDelegate.MediaSource>?,
            callback: GeckoSession.PermissionDelegate.MediaCallback
        ) {
            val mic = audio?.firstOrNull {
                it.source == GeckoSession.PermissionDelegate.MediaSource.SOURCE_MICROPHONE
            }
            val androidGranted = checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            if (isTrustedChatGptOrigin(uri) && video.isNullOrEmpty() && mic != null && androidGranted) {
                callback.grant(null as GeckoSession.PermissionDelegate.MediaSource?, mic)
                showStatus("Microfoon actief", 1_800L)
            } else {
                callback.reject()
                if (!androidGranted) showStatus("Geef Raise AI microfoontoegang", 4_000L)
            }
        }
    }

    private fun ensureMicrophonePermission() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MICROPHONE)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_MICROPHONE) return
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        pendingAndroidPermission?.let { if (granted) it.grant() else it.reject() }
        pendingAndroidPermission = null
        showStatus(
            if (granted) "Microfoon toegestaan" else "Microfoon geweigerd · typen werkt wel",
            3_000L
        )
    }

    private fun showStatus(message: String, hideAfterMs: Long = 0L) {
        handler.removeCallbacksAndMessages(STATUS_TOKEN)
        statusPill.text = message
        statusPill.visibility = View.VISIBLE
        if (hideAfterMs > 0L) {
            handler.postAtTime(
                { statusPill.visibility = View.GONE },
                STATUS_TOKEN,
                android.os.SystemClock.uptimeMillis() + hideAfterMs
            )
        }
    }

    @Deprecated("Android Activity back navigation")
    override fun onBackPressed() {
        if (::session.isInitialized && canGoBack) session.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        pendingAndroidPermission?.reject()
        pendingAndroidPermission = null
        if (::geckoView.isInitialized) geckoView.releaseSession()
        if (::session.isInitialized && session.isOpen) session.close()
        super.onDestroy()
    }

    private fun isTrustedChatGptOrigin(value: String): Boolean = runCatching {
        val uri = Uri.parse(value)
        val host = uri.host?.lowercase() ?: return@runCatching false
        uri.scheme == "https" && (host == "chatgpt.com" || host.endsWith(".chatgpt.com") ||
            host == "chat.openai.com" || host.endsWith(".chat.openai.com"))
    }.getOrDefault(false)

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    companion object {
        const val EXTRA_TRY_WEBSITE_MIC = "try_website_mic"
        private const val CHATGPT_URL = "https://chatgpt.com/"
        private const val EXTENSION_URI = "resource://android/assets/raiseai_wear/"
        private const val EXTENSION_ID = "raiseai-wear@zennay.nl"
        private const val REQUEST_MICROPHONE = 808
        private val STATUS_TOKEN = Any()
    }
}

/** Process-wide Gecko runtime: cookies and sign-in survive individual Activity sessions. */
private object GeckoEngine {
    @Volatile private var instance: GeckoRuntime? = null

    fun runtime(activity: Activity): GeckoRuntime = instance ?: synchronized(this) {
        instance ?: GeckoRuntime.create(activity.applicationContext).also { instance = it }
    }
}
