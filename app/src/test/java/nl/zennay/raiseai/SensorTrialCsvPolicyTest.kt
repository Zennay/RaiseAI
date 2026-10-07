package nl.zennay.raiseai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorTrialCsvPolicyTest {
    private val revision = "0123456789abcdef0123456789abcdef01234567"
    private val detector = "raise-detector-v1;similarity=0.955"

    @Test
    fun canonicalHeaderIsExact() {
        assertTrue(SensorTrialCsvPolicy.hasCanonicalHeader(SensorTrialCsvPolicy.HEADER))
        assertFalse(
            SensorTrialCsvPolicy.hasCanonicalHeader(
                "label,duration_ms,session_id,sample_count,detector_triggered,max_similarity,app_version,source_revision,detector_config"
            )
        )
    }

    @Test
    fun canonicalRowParsesAndNormalizesRevision() {
        val parsed = SensorTrialCsvPolicy.parseRow(
            "mouth_raise,123,4000,40,true,0.98,1.5.2," + revision.uppercase() + "," + detector
        )

        requireNotNull(parsed)
        assertEquals("mouth_raise", parsed.label)
        assertEquals(123L, parsed.sessionId)
        assertEquals(40, parsed.sampleCount)
        assertTrue(parsed.detectorTriggered)
        assertEquals(revision, parsed.sourceRevision)
    }

    @Test
    fun rejectsInvalidIdentityAndTiming() {
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,0,4000,40,true,0.98,1.5.2," + revision + "," + detector
            )
        )
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,-1,40,true,0.98,1.5.2," + revision + "," + detector
            )
        )
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "unknown,123,4000,40,true,0.98,1.5.2," + revision + "," + detector
            )
        )
    }

    @Test
    fun rejectsExtraCsvColumnsHiddenInDetectorConfig() {
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,4000,40,true,0.98,1.5.2," + revision + "," + detector + ",unexpected"
            )
        )
    }

    @Test
    fun rejectsSimilarityOutsideDetectorDomain() {
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,4000,40,true,1.01,1.5.2," + revision + "," + detector
            )
        )
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,4000,40,true,-1.01,1.5.2," + revision + "," + detector
            )
        )
    }

    @Test
    fun rejectsNonFiniteSimilarityAndMalformedRevision() {
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,4000,40,true,NaN,1.5.2," + revision + "," + detector
            )
        )
        assertNull(
            SensorTrialCsvPolicy.parseRow(
                "mouth_raise,123,4000,40,true,0.98,1.5.2,not-a-revision," + detector
            )
        )
    }
}
