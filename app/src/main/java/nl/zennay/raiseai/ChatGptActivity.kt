package nl.zennay.raiseai

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
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
 * Voice-first Wear shell around the official ChatGPT website.
 *
 * The bundled WebExtension owns the visible microphone UI and the website interaction.
 * Native code keeps Gecko warm, forwards clean gesture events, and grants microphone access
 * only to trusted ChatGPT origins.
 */
class ChatGptActivity : Activity() {
    private lateinit var geckoView: GeckoView
    private lateinit var session: GeckoSession
    private lateinit var statusPill: TextView
    private val handler = Handler(Looper.getMainLooper())

    private var canGoBack = false
    private var pendingAndroidPermission: GeckoSession.PermissionDelegate.Callback? = null
    private var autoStartRequested = false
    private var lastNavigationUrl: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        autoStartRequested = intent.getBooleanExtra(EXTRA_TRY_WEBSITE_MIC, false)

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

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)

        if (intent.getBooleanExtra(EXTRA_TRY_WEBSITE_MIC, false)) {
            autoStartRequested = true
            val accepted = WearBridge.requestStart("gesture")
            if (accepted) {
                showStatus("Microfoon starten…", 1_200L)
            } else {
                showStatus("Ik luister al", 900L)
            }
        }
    }

    private fun buildUi(): FrameLayout {
        geckoView = GeckoView(this).apply {
            setBackgroundColor(Color.BLACK)
            overScrollMode = View.OVER_SCROLL_NEVER
        }

        statusPill = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(232, 28, 28, 31))
            textSize = 11f
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(6), dp(12), dp(6))
        }

        return FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(
                geckoView,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
            )
            addView(
                statusPill,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    Gravity.TOP or Gravity.CENTER_HORIZONTAL
                ).apply {
                    topMargin = dp(9)
                    marginStart = dp(38)
                    marginEnd = dp(38)
                }
            )
        }
    }

    private fun startGecko() {
        showStatus("Raise AI starten…")
        val runtime = GeckoEngine.runtime(this)
        val lease = ChatSessionCache.acquire(runtime)

        session = lease.session
        bindSessionDelegates()
        geckoView.setSession(session)
        WearBridge.markLoading()

        runtime.webExtensionController.ensureBuiltIn(EXTENSION_URI, EXTENSION_ID).accept(
            { extension ->
                WearBridge.attach(session, extension)

                if (lease.needsInitialLoad) {
                    ChatSessionCache.markNavigationStarted(session)
                    session.loadUri(CHATGPT_URL)
                }

                if (autoStartRequested) {
                    WearBridge.requestStart("launch")
                }
            },
            {
                showStatus("Wear UI kon niet laden · opnieuw proberen", 5_000L)
                if (lease.needsInitialLoad) {
                    ChatSessionCache.markNavigationStarted(session)
                    session.loadUri(CHATGPT_URL)
                }
            }
        )
    }

    private fun bindSessionDelegates() {
        session.permissionDelegate = permissionDelegate()
        session.navigationDelegate = object : GeckoSession.NavigationDelegate {
            override fun onCanGoBack(session: GeckoSession, value: Boolean) {
                canGoBack = value
            }
        }
        session.progressDelegate = object : GeckoSession.ProgressDelegate {
            override fun onPageStart(session: GeckoSession, url: String) {
                lastNavigationUrl = url
                WearBridge.markLoading()
                showStatus(
                    if (isTrustedChatGptOrigin(url)) "ChatGPT laden…" else "Veilig inloggen…"
                )
            }

            override fun onPageStop(session: GeckoSession, success: Boolean) {
                if (success) {
                    ChatSessionCache.markPageAvailable(session)
                    if (isTrustedChatGptOrigin(lastNavigationUrl)) {
                        showStatus("Klaar", 900L)
                        if (autoStartRequested) {
                            WearBridge.requestStart("page-ready")
                            autoStartRequested = false
                        }
                    } else {
                        showStatus("Rond de login af · daarna ga ik vanzelf verder", 3_000L)
                    }
                } else {
                    ChatSessionCache.markLoadFailed(session)
                    showStatus("Laden mislukt · controleer wifi", 5_000L)
                }
            }
        }
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
            } else if (
                checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            ) {
                callback.grant()
            } else {
                pendingAndroidPermission?.reject()
                pendingAndroidPermission = callback
                requestPermissions(
                    arrayOf(Manifest.permission.RECORD_AUDIO),
                    REQUEST_MICROPHONE
                )
            }
        }

        override fun onContentPermissionRequest(
            session: GeckoSession,
            permission: GeckoSession.PermissionDelegate.ContentPermission
        ): GeckoResult<Int> {
            val trusted = isTrustedChatGptOrigin(permission.uri)
            val allowedType =
                permission.permission ==
                    GeckoSession.PermissionDelegate.PERMISSION_PERSISTENT_STORAGE ||
                permission.permission ==
                    GeckoSession.PermissionDelegate.PERMISSION_AUTOPLAY_INAUDIBLE

            return GeckoResult.fromValue(
                if (trusted && allowedType) {
                    GeckoSession.PermissionDelegate.ContentPermission.VALUE_ALLOW
                } else {
                    GeckoSession.PermissionDelegate.ContentPermission.VALUE_DENY
                }
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
            val androidGranted =
                checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                    PackageManager.PERMISSION_GRANTED

            if (
                isTrustedChatGptOrigin(uri) &&
                video.isNullOrEmpty() &&
                mic != null &&
                androidGranted
            ) {
                callback.grant(
                    null as GeckoSession.PermissionDelegate.MediaSource?,
                    mic
                )
                showStatus("Luisteren…", 1_200L)
            } else {
                callback.reject()
                if (!androidGranted) {
                    showStatus("Geef Raise AI microfoontoegang", 4_000L)
                }
            }
        }
    }

    private fun ensureMicrophonePermission() {
        if (
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.RECORD_AUDIO),
                REQUEST_MICROPHONE
            )
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
        pendingAndroidPermission?.let {
            if (granted) it.grant() else it.reject()
        }
        pendingAndroidPermission = null

        showStatus(
            if (granted) "Microfoon toegestaan" else "Microfoon geweigerd",
            2_500L
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
        if (::session.isInitialized && canGoBack) {
            session.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        pendingAndroidPermission?.reject()
        pendingAndroidPermission = null

        if (::session.isInitialized) {
            session.permissionDelegate = null
            session.navigationDelegate = null
            session.progressDelegate = null
        }

        if (::geckoView.isInitialized) {
            geckoView.releaseSession()
        }

        if (::session.isInitialized) {
            ChatSessionCache.releaseLater(session)
        }

        super.onDestroy()
    }

    private fun isTrustedChatGptOrigin(value: String): Boolean = runCatching {
        val uri = Uri.parse(value)
        val host = uri.host?.lowercase() ?: return@runCatching false
        uri.scheme == "https" && (
            host == "chatgpt.com" ||
            host.endsWith(".chatgpt.com") ||
            host == "chat.openai.com" ||
            host.endsWith(".chat.openai.com")
        )
    }.getOrDefault(false)

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).roundToInt()

    companion object {
        const val EXTRA_TRY_WEBSITE_MIC = "try_website_mic"
        private const val CHATGPT_URL = "https://chatgpt.com/"
        private const val EXTENSION_URI = "resource://android/assets/raiseai_wear/"
        private const val EXTENSION_ID = "raiseai-wear@zennay.nl"
        private const val REQUEST_MICROPHONE = 808
        private val STATUS_TOKEN = Any()
    }
}

/** Process-wide Gecko runtime. The foreground gesture service can prewarm only the engine. */
object GeckoEngine {
    @Volatile
    private var instance: GeckoRuntime? = null

    fun runtime(context: Context): GeckoRuntime =
        instance ?: synchronized(this) {
            instance ?: GeckoRuntime.create(context.applicationContext).also {
                instance = it
            }
        }

    fun prewarm(context: Context) {
        runtime(context)
    }
}

/**
 * Keeps the already loaded ChatGPT page alive briefly after leaving the Activity.
 *
 * Ten minutes gives fast repeat interactions without running a full hidden browser page forever.
 * The foreground gesture service keeps only Gecko's engine warm outside this window.
 */
private object ChatSessionCache {
    private const val KEEP_WARM_MS = 10L * 60L * 1_000L

    data class Lease(
        val session: GeckoSession,
        val needsInitialLoad: Boolean
    )

    private val handler = Handler(Looper.getMainLooper())
    private var cachedSession: GeckoSession? = null
    private var pageAvailable = false

    private val closeRunnable = Runnable {
        val closing = cachedSession
        cachedSession = null
        pageAvailable = false

        if (closing != null) {
            WearBridge.onSessionClosed(closing)
            if (closing.isOpen) {
                runCatching { closing.close() }
            }
        }
    }

    fun acquire(runtime: GeckoRuntime): Lease {
        handler.removeCallbacks(closeRunnable)

        val existing = cachedSession
        if (existing != null && existing.isOpen) {
            return Lease(existing, needsInitialLoad = !pageAvailable)
        }

        val created = GeckoSession()
        created.open(runtime)
        cachedSession = created
        pageAvailable = false
        return Lease(created, needsInitialLoad = true)
    }

    fun markNavigationStarted(session: GeckoSession) {
        if (cachedSession === session) pageAvailable = true
    }

    fun markPageAvailable(session: GeckoSession) {
        if (cachedSession === session) pageAvailable = true
    }

    fun markLoadFailed(session: GeckoSession) {
        if (cachedSession === session) pageAvailable = false
    }

    fun releaseLater(session: GeckoSession) {
        if (cachedSession !== session) return
        handler.removeCallbacks(closeRunnable)
        handler.postDelayed(closeRunnable, KEEP_WARM_MS)
    }
}
