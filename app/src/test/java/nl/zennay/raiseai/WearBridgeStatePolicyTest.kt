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
}
