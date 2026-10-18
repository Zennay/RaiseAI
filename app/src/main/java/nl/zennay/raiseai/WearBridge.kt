package nl.zennay.raiseai

import android.util.Log
import org.json.JSONObject
import org.mozilla.geckoview.GeckoSession
import org.mozilla.geckoview.WebExtension

object WearBridge {
    private const val TAG = "RaiseAI.WearBridge"
    private const val NATIVE_APP = "raiseai"
    private val busyStates = setOf("starting", "listening", "finalizing", "sending", "speaking")

    @Volatile private var attachedSession: GeckoSession? = null
    @Volatile private var port: WebExtension.Port? = null
    @Volatile private var pendingStartReason: String? = null
    @Volatile private var currentState: String = "cold"
    @Volatile private var assistantReplyHandler: ((String) -> Unit)? = null

    private val portDelegate = object : WebExtension.PortDelegate {
        override fun onPortMessage(message: Any, port: WebExtension.Port) {
            if (port !== this@WearBridge.port) return
            val json = message as? JSONObject ?: return
            when (json.optString("type")) {
                "state" -> {
                    val state = WearBridgeStatePolicy.normalizeInboundState(
                        json.optString("state")
                    )
                    currentState = state
                    Log.d(TAG, "Wear state -> " + state)
                }
                "assistantReply" -> {
                    val reply = json.optString("text").trim()
                    if (reply.isBlank()) return
                    val handler = assistantReplyHandler
                    if (handler != null) handler(reply) else setSpeaking(false)
                }
            }
        }

        override fun onDisconnect(port: WebExtension.Port) {
            markDisconnected(port)
        }
    }

    private val messageDelegate = object : WebExtension.MessageDelegate {
        override fun onConnect(port: WebExtension.Port) {
            val expected = attachedSession
            if (expected == null || port.sender.session !== expected || port.name != NATIVE_APP) {
                port.disconnect()
                return
            }
            this@WearBridge.port = port
            port.setDelegate(portDelegate)
            pendingStartReason?.let { reason ->
                pendingStartReason = null
                postStart(port, reason)
            }
        }
    }

    fun attach(session: GeckoSession, extension: WebExtension) {
        attachedSession = session
        session.webExtensionController.setMessageDelegate(extension, messageDelegate, NATIVE_APP)
    }

    fun setAssistantReplyHandler(handler: ((String) -> Unit)?) {
        assistantReplyHandler = handler
    }

    fun markLoading() {
        if (currentState !in busyStates) currentState = "loading"
    }

    fun requestStart(reason: String): Boolean {
        if (!WearBridgeStatePolicy.acceptsStartRequest(
                state = currentState,
                reason = reason,
                active = currentState in busyStates
            )
        ) {
            return false
        }
        val currentPort = port
        if (currentPort == null) {
            pendingStartReason = reason
            return true
        }
        postStart(currentPort, reason)
        return true
    }

    fun setSpeaking(speaking: Boolean) {
        val currentPort = port
        currentState = WearBridgeStatePolicy.stateAfterSpeakingUpdate(
            speaking = speaking,
            connected = currentPort != null
        )
        if (currentPort == null) return
        runCatching {
            currentPort.postMessage(JSONObject().apply {
                put("type", "ttsState")
                put("speaking", speaking)
            })
        }.onFailure {
            markDisconnected(currentPort)
        }
    }

    fun shouldBlockGesture(): Boolean = WearBridgeStatePolicy.blocksGesture(currentState)
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
            port.postMessage(JSONObject().apply {
                put("type", "startDictation")
                put("reason", reason)
            })
            currentState = "starting"
        }.onFailure {
            markDisconnected(port)
            pendingStartReason = reason
        }
    }

    private fun markDisconnected(disconnectedPort: WebExtension.Port) {
        if (port === disconnectedPort) {
            port = null
            currentState = "disconnected"
        }
    }
}
