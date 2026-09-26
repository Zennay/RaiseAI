package nl.zennay.raiseai

import android.util.Log
import org.json.JSONObject
import org.mozilla.geckoview.GeckoSession
import org.mozilla.geckoview.WebExtension

/**
 * Small process-wide bridge between the Wear UI WebExtension and the native gesture service.
 *
 * The WebExtension owns the website interaction. Native code only sends high-level commands
 * such as "start dictation" and receives coarse session state so a second wrist gesture cannot
 * restart the microphone while the first utterance is still active.
 */
object WearBridge {
    private const val TAG = "RaiseAI.WearBridge"
    private const val NATIVE_APP = "raiseai"

    private val busyStates = setOf("starting", "listening", "finalizing", "sending")

    @Volatile
    private var attachedSession: GeckoSession? = null

    @Volatile
    private var port: WebExtension.Port? = null

    @Volatile
    private var pendingStartReason: String? = null

    @Volatile
    private var currentState: String = "cold"

    private val portDelegate = object : WebExtension.PortDelegate {
        override fun onPortMessage(message: Any, port: WebExtension.Port) {
            if (port !== this@WearBridge.port) return
            val json = message as? JSONObject ?: return
            if (json.optString("type") != "state") return

            val state = json.optString("state")
            if (state in setOf(
                    "loading",
                    "ready",
                    "starting",
                    "listening",
                    "finalizing",
                    "sending",
                    "disconnected"
                )
            ) {
                currentState = state
                Log.d(TAG, "Wear state -> $state")
            }
        }

        override fun onDisconnect(port: WebExtension.Port) {
            if (port === this@WearBridge.port) {
                this@WearBridge.port = null
                currentState = "disconnected"
            }
        }
    }

    private val messageDelegate = object : WebExtension.MessageDelegate {
        override fun onConnect(port: WebExtension.Port) {
            val expected = attachedSession
            if (expected == null || port.sender.session !== expected || port.name != NATIVE_APP) {
                Log.w(TAG, "Rejected unexpected Wear bridge port")
                port.disconnect()
                return
            }

            this@WearBridge.port = port
            port.setDelegate(portDelegate)
            Log.d(TAG, "Wear bridge connected")

            pendingStartReason?.let { reason ->
                pendingStartReason = null
                postStart(port, reason)
            }
        }
    }

    fun attach(session: GeckoSession, extension: WebExtension) {
        attachedSession = session
        session.webExtensionController.setMessageDelegate(
            extension,
            messageDelegate,
            NATIVE_APP
        )
    }

    fun markLoading() {
        if (currentState !in busyStates) currentState = "loading"
    }

    fun requestStart(reason: String): Boolean {
        if (currentState in busyStates) {
            Log.d(TAG, "Ignoring start while state=$currentState")
            return false
        }

        val currentPort = port
        if (currentPort == null) {
            pendingStartReason = reason
            Log.d(TAG, "Queued dictation start until Wear bridge connects")
            return true
        }

        postStart(currentPort, reason)
        return true
    }

    fun shouldBlockGesture(): Boolean = currentState in busyStates || currentState == "loading"

    fun state(): String = currentState

    fun onSessionClosed(session: GeckoSession) {
        if (attachedSession === session) {
            runCatching { port?.disconnect() }
            port = null
            attachedSession = null
            pendingStartReason = null
            currentState = "cold"
        }
    }

    private fun postStart(port: WebExtension.Port, reason: String) {
        runCatching {
            port.postMessage(
                JSONObject().apply {
                    put("type", "startDictation")
                    put("reason", reason)
                }
            )
            currentState = "starting"
        }.onFailure {
            Log.w(TAG, "Could not send dictation start", it)
            if (this.port === port) this.port = null
            pendingStartReason = reason
            currentState = "disconnected"
        }
    }
}
