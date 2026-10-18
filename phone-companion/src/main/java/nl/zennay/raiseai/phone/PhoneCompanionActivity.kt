package nl.zennay.raiseai.phone

import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.MessageEvent

/**
 * Explicit and visible operator control: no background starts, no ChatGPT account credentials,
 * and no unsupported Voice/Watch audio routing.
 */
class PhoneCompanionActivity : Activity() {
    private lateinit var wearStatus: TextView
    private var watchLookupGeneration = 0
    private var companionVisible = false
    private var pendingWatchRequest: OfficialChatGptPhoneHandoffPolicy.Request? = null
    private val requestPolicy = OfficialChatGptPhoneHandoffPolicy()
    private val wearListener = MessageClient.OnMessageReceivedListener { event ->
        handleWearRequest(event)
    }

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
        note("Check the paired Watch connection here. Connection alone does not prove APK " +
            "signing parity, command delivery or ChatGPT Voice audio routing.")
        note("If the Watch sends a valid foreground-only handoff request, you must still " +
            "verify the publisher and tap the launch button here within 15 seconds. " +
            "Nothing starts automatically and Voice must be selected manually.")
        wearStatus = note("Watch connection not checked yet.", 14f)
        container.addView(Button(this).apply {
            text = "Check paired Watch"
            isAllCaps = false
            setOnClickListener { inspectWearConnection() }
        })
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
                // Never persist or transmit a publisher fingerprint. Every launch, including
                // user-approved Watch requests, repeats the actual installed-app signer check.
                val expected = fingerprint.text.toString().trim()
                val launcher = OfficialChatGptLauncher(this@PhoneCompanionActivity)
                val incoming = pendingWatchRequest
                if (incoming != null) {
                    pendingWatchRequest = null
                    val signed = launcher.verifyInstalledPublisher(expected) ==
                        OfficialChatGptLauncher.Result.VERIFIED_OFFICIAL_APP
                    val decision = requestPolicy.decide(
                        request = incoming,
                        trustedSender = true, // Established by Data Layer + unique nearby source node.
                        userConsented = true, // This foreground phone button, never a Wear message.
                        verifiedOfficialApp = signed,
                        nowEpochMs = System.currentTimeMillis()
                    )
                    if (decision != OfficialChatGptPhoneHandoffPolicy.Decision.OPEN_OFFICIAL_APP) {
                        status.text = "Watch request rejected ($decision). " +
                            "No app opened. Check Watch connection and publisher certificate."
                        return@setOnClickListener
                    }
                }
                val result = launcher.launchOnExplicitButtonTap(expected)
                status.text = when (result) {
                    OfficialChatGptLauncher.Result.OPENED_OFFICIAL_APP ->
                        "Official package signature matches your reference. " +
                        "ChatGPT opened; manually tap Voice within the official app."
                    OfficialChatGptLauncher.Result.VERIFIED_OFFICIAL_APP ->
                        "Publisher verified; no launch was requested."
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
        inspectWearConnection()
    }

    override fun onStart() {
        super.onStart()
        companionVisible = true
        // Listen only while the person is actively using the phone companion.
        // No background service, background app launch, audio or WakeLock is installed.
        try {
            Wearable.getMessageClient(this).addListener(
                wearListener,
                Uri.parse("wear://*$WATCH_REQUEST_PATH"),
                MessageClient.FILTER_LITERAL
            ).addOnFailureListener {
                if (companionVisible && !isFinishing && !isDestroyed) {
                    wearStatus.text = "Wear request listener unavailable. " +
                        "Open the companion and verify the paired Watch connection."
                }
            }
        } catch (_: RuntimeException) {
            wearStatus.text = "Wear request listener unavailable; manual launch remains available."
        }
    }

    override fun onStop() {
        companionVisible = false
        pendingWatchRequest = null
        ++watchLookupGeneration
        try {
            Wearable.getMessageClient(this).removeListener(wearListener)
        } catch (_: RuntimeException) {
            // The listener is foreground-bound and no incoming packet can launch an app.
        }
        super.onStop()
    }

    private fun handleWearRequest(event: MessageEvent) {
        if (!companionVisible || event.path != WATCH_REQUEST_PATH) return
        val request = OfficialChatGptPhoneHandoffWireCodec.decode(event.data) ?: return
        val now = System.currentTimeMillis()
        // The payload is untrusted even though transport is app-scoped. Drop stale packets
        // before showing anything, and never interpret packet content as an Android Intent.
        if (request.issuedAtEpochMs > now) {
            if (request.issuedAtEpochMs - now > MAX_FUTURE_MS) return
        } else if (now - request.issuedAtEpochMs > MAX_REQUEST_AGE_MS) return
        val senderNodeId = event.sourceNodeId
        val generation = watchLookupGeneration
        try {
            Wearable.getNodeClient(this).connectedNodes
                .addOnSuccessListener { nodes ->
                    if (!companionVisible || generation != watchLookupGeneration ||
                        isFinishing || isDestroyed
                    ) return@addOnSuccessListener
                    val nearby = nodes.filter { it.isNearby }
                    if (nearby.size != 1 || nearby.single().id != senderNodeId) {
                        wearStatus.text = "Unverified Watch source or multiple nearby devices. " +
                            "No handoff request accepted."
                        return@addOnSuccessListener
                    }
                    val existing = pendingWatchRequest
                    if (existing != null && now - existing.issuedAtEpochMs <= MAX_REQUEST_AGE_MS) {
                        wearStatus.text = "A Watch request is already pending. " +
                            "Approve it on this phone or let it expire."
                        return@addOnSuccessListener
                    }
                    pendingWatchRequest = request
                    wearStatus.text = "Watch request received from the only nearby connected " +
                        "device. Enter your independently trusted publisher fingerprint and " +
                        "tap the phone's Verify/Open button now. Voice is still manual."
                }
        } catch (_: RuntimeException) {
            wearStatus.text = "Watch identity unavailable. No request accepted."
        }
    }

    private fun inspectWearConnection() {
        // A connected Data Layer node is not automatically a verified, authorised Watch.
        // Never persist node names/IDs or use this discovery to start the ChatGPT app.
        val generation = ++watchLookupGeneration
        wearStatus.text = "Checking Google Play Services / Wear connection…"
        try {
            Wearable.getNodeClient(this).connectedNodes
                .addOnSuccessListener { nodes ->
                    if (generation != watchLookupGeneration || isFinishing || isDestroyed) {
                        return@addOnSuccessListener
                    }
                    val nearby = nodes.count { it.isNearby }
                    wearStatus.text = when {
                        nodes.isEmpty() -> "No connected Wear device. Pair and connect your Watch 7 first."
                        nearby == 1 && nodes.size == 1 ->
                            "One nearby Wear device is connected. Check that Raise AI is installed " +
                                "on both devices with the same application ID and signing key."
                        nearby > 0 ->
                            "$nearby nearby Wear devices among ${nodes.size} connected. " +
                                "Choose and verify the intended Watch before any future handoff."
                        else ->
                            "${nodes.size} Wear device(s) linked, none currently nearby. " +
                                "Open the Watch connection before starting a handoff."
                    }
                }
                .addOnFailureListener {
                    if (generation == watchLookupGeneration && !isFinishing && !isDestroyed) {
                        wearStatus.text = "Wear connection could not be checked. " +
                            "Confirm that Google Play Services and the paired Watch are available."
                    }
                }
        } catch (_: RuntimeException) {
            wearStatus.text = "Wear support unavailable on this phone. " +
                "Manual official-app verification remains available."
        }
    }

    override fun onDestroy() {
        ++watchLookupGeneration
        super.onDestroy()
    }

    private companion object {
        const val WATCH_REQUEST_PATH = "/raiseai/official-chatgpt/request-v1"
        const val MAX_REQUEST_AGE_MS = OfficialChatGptPhoneHandoffPolicy.MAX_AGE_MS
        const val MAX_FUTURE_MS = OfficialChatGptPhoneHandoffPolicy.FUTURE_SKEW_MS
    }
}
