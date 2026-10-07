package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTraceRecorderTest {
    @Test
    fun acceptsValidTraceSample() {
        assertTrue(
            SensorTraceRecorder.isValidSample(
                label = "mouth_raise",
                sessionId = 1,
                elapsedMs = 0,
                x = 0.1f,
                y = -9.7f,
                z = 0.3f
            )
        )
    }

    @Test
    fun rejectsNonFiniteAxes() {
        assertFalse(SensorTraceRecorder.isValidSample("mouth_raise", 1, 0, Float.NaN, 0f, 0f))
        assertFalse(SensorTraceRecorder.isValidSample("mouth_raise", 1, 0, 0f, Float.POSITIVE_INFINITY, 0f))
        assertFalse(SensorTraceRecorder.isValidSample("mouth_raise", 1, 0, 0f, 0f, Float.NEGATIVE_INFINITY))
    }

    @Test
    fun sampleCountIgnoresMalformedAndNonFiniteRows() {
        val count = SensorTraceRecorder.validSampleLineCount(
            sequenceOf(
                "label,session_id,elapsed_ms,x,y,z",
                "mouth_raise,1,0,0.1,-9.7,0.3",
                "view_time,2,10,NaN,0.0,9.81",
                "broken,row",
                "",
                "normal_move,3,25,0.0,0.1,9.7"
            )
        )

        assertTrue(count == 2)
    }

    @Test
    fun sampleCountRejectsInvalidIdentityAndTimingRows() {
        val count = SensorTraceRecorder.validSampleLineCount(
            sequenceOf(
                "label,session_id,elapsed_ms,x,y,z",
                "unexpected,1,0,0.0,0.0,9.81",
                "view_time,0,0,0.0,0.0,9.81",
                "normal_move,3,-1,0.0,0.0,9.81"
            )
        )

        assertTrue(count == 0)
    }

    @Test
    fun rejectsInvalidIdentityAndTiming() {
        assertFalse(SensorTraceRecorder.isValidSample("unexpected", 1, 0, 0f, 0f, 9.81f))
        assertFalse(SensorTraceRecorder.isValidSample("view_time", 0, 0, 0f, 0f, 9.81f))
        assertFalse(SensorTraceRecorder.isValidSample("normal_move", 1, -1, 0f, 0f, 9.81f))
    }
}
