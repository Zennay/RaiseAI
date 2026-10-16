package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTrialCsvPolicyTest {
    private val revision = "a".repeat(40)
    private fun row(
        label: String = "mouth_raise",
        sessionId: String = "12345",
        duration: String = "4000",
        samples: String = "40",
        triggered: String = "true",
        similarity: String = "0.88",
        version: String = "1.5.3",
        source: String = revision,
        detector: String = "detector-v1"
    ) = listOf(label, sessionId, duration, samples, triggered, similarity, version, source, detector)
        .joinToString(",")

    private fun parse(vararg entries: String): SensorTrialProgress =
        SensorTrialCsvPolicy.evaluate(sequenceOf(SensorTrialCsvPolicy.HEADER, *entries))

    @Test fun validMouthAndNonTriggerEvidenceCountsSeparately() {
        val progress = parse(row(), row(label = "normal_move", sessionId = "12346", triggered = "false"))
        assertEquals(1, progress.mouthTrials)
        assertEquals(1, progress.mouthDetections)
        assertEquals(1, progress.nonTriggerTrials)
        assertEquals(0, progress.falseTriggers)
        assertEquals(0, progress.rejectedTrials)
    }

    @Test fun duplicateSessionCannotInflateCounters() {
        val progress = parse(row(), row(sessionId = "12345", label = "view_time"))
        assertEquals(1, progress.mouthTrials)
        assertEquals(0, progress.nonTriggerTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.v1GatePassed)
    }

    @Test fun allThirtyAndHundredUniqueSessionsPassAtThreshold() {
        val mouth = (1..30).map { row(sessionId = "$it", triggered = if (it <= 27) "true" else "false") }
        val movement = (31..130).map {
            row(label = "normal_move", sessionId = "$it", triggered = if (it <= 35) "true" else "false")
        }
        val result = SensorTrialCsvPolicy.evaluate(
            sequenceOf(SensorTrialCsvPolicy.HEADER) + (mouth + movement).asSequence()
        )
        assertTrue(result.v1GatePassed)
    }

    @Test fun malformedHeaderNeverPasses() {
        assertEquals(1, SensorTrialCsvPolicy.evaluate(emptySequence()).rejectedTrials)
        assertEquals(1, SensorTrialCsvPolicy.evaluate(sequenceOf("bad header", row())).rejectedTrials)
    }

    @Test fun duplicateMakesOtherwisePassingDatasetFail() {
        val records = (1..30).map { row(sessionId = "$it") } +
            (31..130).map { row(label = "view_time", sessionId = "$it", triggered = "false") }
        val progress = SensorTrialCsvPolicy.evaluate(
            sequenceOf(SensorTrialCsvPolicy.HEADER) + records.asSequence() +
                sequenceOf(row(sessionId = "1"))
        )
        assertEquals(30, progress.mouthTrials)
        assertEquals(100, progress.nonTriggerTrials)
        assertEquals(1, progress.rejectedTrials)
        assertFalse(progress.v1GatePassed)
    }

    @Test fun rejectsInvalidNumericAndIdentityFields() {
        val invalid = listOf(
            row(sessionId = "0"), row(sessionId = "-12"), row(sessionId = "oops"),
            row(duration = "2999"), row(duration = "-1"), row(samples = "19"),
            row(samples = "oops"), row(triggered = "TRUE"), row(similarity = "NaN"),
            row(similarity = "Infinity"), row(similarity = "1.1"), row(similarity = "-1.1"),
            row(similarity = "wrong"), row(version = ""), row(source = "unknown"),
            row(source = "z".repeat(40)), row(detector = "missing"), row(detector = " ")
        )
        val progress = SensorTrialCsvPolicy.evaluate(
            sequenceOf(SensorTrialCsvPolicy.HEADER) + invalid.asSequence()
        )
        assertEquals(invalid.size, progress.rejectedTrials)
        assertEquals(0, progress.mouthTrials)
    }

    @Test fun unknownLabelAndAdditionalColumnsAreRejected() {
        val result = parse(row(label = "synthetic"), row() + ",injected")
        assertEquals(2, result.rejectedTrials)
    }

    @Test fun fullCanonicalDetectorFingerprintIsAccepted() {
        // configurationId() contains all threshold and timing fields, not only the version.
        val detector = listOf(
            "raise-detector-v1",
            "similarity=0.955", "rearmSimilarity=0.9", "movement=0.85",
            "holdMs=200", "movementWindowMs=1400", "movementBurstMs=700",
            "movementHits=2", "approachStart=0.92", "approachWindowMs=1900",
            "minimumApproachRise=0.025", "cooldownMs=2500", "rearmHoldMs=500"
        ).joinToString(";")
        assertTrue(detector.length > 128)
        assertEquals(0, parse(row(detector = detector)).rejectedTrials)
        assertEquals(1, parse(row(detector = "x".repeat(1_025))).rejectedTrials)
    }

    @Test fun caseVariantRevisionIsSameEvidenceIdentity() {
        val result = parse(row(source = "A".repeat(40)), row(sessionId = "2", source = revision))
        assertFalse(result.mixedEvidenceIdentity)
        assertEquals(0, result.rejectedTrials)
    }

    @Test fun oldBuildEvidenceCannotQualifyAsCurrentWatchProgress() {
        val expected = SensorTrialIdentity("1.5.3", revision, "detector-v1")
        val valid = SensorTrialCsvPolicy.evaluate(
            sequenceOf(SensorTrialCsvPolicy.HEADER, row()), expected
        )
        assertEquals(1, valid.mouthTrials)
        assertEquals(0, valid.rejectedTrials)

        for (stale in listOf(
            row(version = "1.5.2"),
            row(source = "b".repeat(40)),
            row(detector = "detector-v2")
        )) {
            val result = SensorTrialCsvPolicy.evaluate(
                sequenceOf(SensorTrialCsvPolicy.HEADER, stale), expected
            )
            assertEquals(0, result.mouthTrials)
            assertEquals(1, result.rejectedTrials)
            assertFalse(result.v1GatePassed)
        }
    }

    @Test fun mixedDetectorSourceOrVersionNeverPasses() {
        val result = parse(
            row(), row(sessionId = "2", detector = "detector-v2"),
            row(sessionId = "3", source = "b".repeat(40)),
            row(sessionId = "4", version = "1.5.4")
        )
        assertTrue(result.mixedEvidenceIdentity)
        assertFalse(result.v1GatePassed)
    }
}
