package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WearBridgeStatePolicyTest {
    @Test
    fun coldAndReadyAllowGestureLaunch() {
        listOf("cold", "ready").forEach { state ->
            assertFalse(
                "expected " + state + " to allow a gesture",
                WearBridgeStatePolicy.blocksGesture(state)
            )
        }
    }

    @Test
    fun activeBridgeStatesBlockGestureLaunch() {
        listOf(
            "loading",
            "starting",
            "listening",
            "finalizing",
            "sending",
            "speaking"
        ).forEach { state ->
            assertTrue(
                "expected " + state + " to block a gesture",
                WearBridgeStatePolicy.blocksGesture(state)
            )
        }
    }

    @Test
    fun disconnectedBridgeFailsClosedUntilReconnect() {
        assertTrue(WearBridgeStatePolicy.blocksGesture("disconnected"))
    }

    @Test
    fun unknownBridgeStatesFailClosed() {
        listOf("", "unexpected", "READY").forEach { state ->
            assertTrue(
                "expected '" + state + "' to block a gesture",
                WearBridgeStatePolicy.blocksGesture(state)
            )
        }
    }

    @Test
    fun speakingStateRequiresConnectedBridge() {
        assertTrue(
            WearBridgeStatePolicy.blocksGesture(
                WearBridgeStatePolicy.stateAfterSpeakingUpdate(
                    speaking = true,
                    connected = true
                )
            )
        )
        assertFalse(
            WearBridgeStatePolicy.blocksGesture(
                WearBridgeStatePolicy.stateAfterSpeakingUpdate(
                    speaking = false,
                    connected = true
                )
            )
        )
    }

    @Test
    fun disconnectedBridgeNeverBecomesReadyFromLateTtsCallback() {
        listOf(true, false).forEach { speaking ->
            val state = WearBridgeStatePolicy.stateAfterSpeakingUpdate(
                speaking = speaking,
                connected = false
            )
            assertTrue(
                "expected disconnected speech update to remain fail closed",
                WearBridgeStatePolicy.blocksGesture(state)
            )
        }
    }

    @Test
    fun knownInboundStatesRemainCanonical() {
        listOf(
            "loading",
            "ready",
            "starting",
            "listening",
            "finalizing",
            "sending",
            "speaking",
            "disconnected"
        ).forEach { state ->
            assertTrue(
                "expected known state to remain unchanged",
                WearBridgeStatePolicy.normalizeInboundState(state) == state
            )
        }
    }

    @Test
    fun unknownInboundStatesNormalizeToBlockedState() {
        listOf("", "transcribing", "READY", "future-state").forEach { state ->
            val normalized = WearBridgeStatePolicy.normalizeInboundState(state)
            assertTrue(
                "expected unknown inbound state to fail closed",
                WearBridgeStatePolicy.blocksGesture(normalized)
            )
            assertTrue(normalized == "unknown")
        }
    }

    @Test
    fun gestureStartsRequireGestureReadyState() {
        listOf("cold", "ready").forEach { state ->
            assertTrue(
                WearBridgeStatePolicy.acceptsStartRequest(
                    state = state,
                    reason = "gesture",
                    active = false
                )
            )
        }

        listOf("loading", "disconnected", "unknown").forEach { state ->
            assertFalse(
                "expected gesture start to be rejected from " + state,
                WearBridgeStatePolicy.acceptsStartRequest(
                    state = state,
                    reason = "gesture",
                    active = false
                )
            )
        }
    }

    @Test
    fun recoveryStartsRemainAvailableUnlessAlreadyActive() {
        listOf("loading", "disconnected", "unknown").forEach { state ->
            assertTrue(
                WearBridgeStatePolicy.acceptsStartRequest(
                    state = state,
                    reason = "launch",
                    active = false
                )
            )
        }
        assertFalse(
            WearBridgeStatePolicy.acceptsStartRequest(
                state = "starting",
                reason = "launch",
                active = true
            )
        )
    }
}
