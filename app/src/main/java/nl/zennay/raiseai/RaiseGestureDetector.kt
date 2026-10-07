package nl.zennay.raiseai

import kotlin.math.min
import kotlin.math.sqrt

data class DetectionDebug(
    val triggered: Boolean,
    val similarity: Float,
    val dynamicAcceleration: Float,
    val armed: Boolean
)

class RaiseGestureDetector {
    private var gravityX = 0f
    private var gravityY = 0f
    private var gravityZ = 9.81f
    private var initialized = false
    private var lastSampleTimeMs: Long? = null
    private var movingUntilMs = 0L
    private var movementBurstStartedMs = 0L
    private var movementHits = 0
    private var poseStartedMs = 0L
    private var outsidePoseStartedMs = 0L
    private var approachPrimedUntilMs = 0L
    private var approachStartSimilarity = 1f
    private var lastSimilarity = 0f
    private var hasSimilarity = false
    private var lastTriggerMs = Long.MIN_VALUE / 2
    private var armed = true

    var similarityThreshold = 0.955f
    var rearmSimilarityThreshold = 0.90f
    var movementThreshold = 0.85f
    var holdMs = 200L
    var movementWindowMs = 1_400L
    var movementBurstMs = 700L
    var requiredMovementHits = 2
    var approachStartSimilarityThreshold = 0.92f
    var approachWindowMs = 1_900L
    var minimumApproachRise = 0.025f
    var cooldownMs = 2_500L
    var rearmHoldMs = 500L

    fun configurationId(): String = listOf(
        "raise-detector-v1",
        "similarity=$similarityThreshold",
        "rearmSimilarity=$rearmSimilarityThreshold",
        "movement=$movementThreshold",
        "holdMs=$holdMs",
        "movementWindowMs=$movementWindowMs",
        "movementBurstMs=$movementBurstMs",
        "movementHits=$requiredMovementHits",
        "approachStart=$approachStartSimilarityThreshold",
        "approachWindowMs=$approachWindowMs",
        "minimumApproachRise=$minimumApproachRise",
        "cooldownMs=$cooldownMs",
        "rearmHoldMs=$rearmHoldMs"
    ).joinToString(";")

    private fun resetTemporalEvidence() {
        movingUntilMs = 0L
        movementBurstStartedMs = 0L
        movementHits = 0
        poseStartedMs = 0L
        outsidePoseStartedMs = 0L
        approachPrimedUntilMs = 0L
        approachStartSimilarity = 1f
    }

    private fun rejectedSample(): DetectionDebug =
        DetectionDebug(
            triggered = false,
            similarity = if (hasSimilarity) lastSimilarity else 0f,
            dynamicAcceleration = 0f,
            armed = armed
        )

    fun onAccelerometer(x: Float, y: Float, z: Float, timeMs: Long, mouthPose: MouthPose?): DetectionDebug {
        val invalidVector = !x.isFinite() || !y.isFinite() || !z.isFinite()
        val invalidMouthPose = mouthPose != null &&
            (!mouthPose.x.isFinite() || !mouthPose.y.isFinite() || !mouthPose.z.isFinite())
        if (invalidVector || invalidMouthPose || timeMs < 0L) {
            resetTemporalEvidence()
            return rejectedSample()
        }

        val previousSampleTimeMs = lastSampleTimeMs
        if (previousSampleTimeMs != null && timeMs <= previousSampleTimeMs) {
            resetTemporalEvidence()
            return rejectedSample()
        }
        lastSampleTimeMs = timeMs

        if (!initialized) {
            // Establish the current wrist orientation as the baseline. Do not count sensor
            // startup/filter settling as an intentional arm movement.
            gravityX = x
            gravityY = y
            gravityZ = z
            initialized = true

            if (mouthPose == null) {
                return DetectionDebug(false, 0f, 0f, armed)
            }

            val length = sqrt(x * x + y * y + z * z).coerceAtLeast(0.001f)
            val initialSimilarity =
                (x / length) * mouthPose.x +
                (y / length) * mouthPose.y +
                (z / length) * mouthPose.z
            lastSimilarity = initialSimilarity
            hasSimilarity = true
            return DetectionDebug(false, initialSimilarity, 0f, armed)
        }

        val alpha = 0.84f
        gravityX = alpha * gravityX + (1f - alpha) * x
        gravityY = alpha * gravityY + (1f - alpha) * y
        gravityZ = alpha * gravityZ + (1f - alpha) * z
        val dx = x - gravityX
        val dy = y - gravityY
        val dz = z - gravityZ
        val dynamic = sqrt(dx * dx + dy * dy + dz * dz)

        if (movementBurstStartedMs != 0L && timeMs - movementBurstStartedMs > movementBurstMs) {
            movementBurstStartedMs = 0L
            movementHits = 0
        }
        if (dynamic >= movementThreshold) {
            if (movementBurstStartedMs == 0L) movementBurstStartedMs = timeMs
            movementHits++
            movingUntilMs = timeMs + movementWindowMs
        }

        if (mouthPose == null) {
            poseStartedMs = 0L
            return DetectionDebug(false, 0f, dynamic, armed)
        }

        val length = sqrt(gravityX * gravityX + gravityY * gravityY + gravityZ * gravityZ).coerceAtLeast(0.001f)
        val similarity = (gravityX / length) * mouthPose.x +
            (gravityY / length) * mouthPose.y +
            (gravityZ / length) * mouthPose.z

        if (!armed) {
            if (similarity < rearmSimilarityThreshold) {
                if (outsidePoseStartedMs == 0L) outsidePoseStartedMs = timeMs
                if (timeMs - outsidePoseStartedMs >= rearmHoldMs &&
                    timeMs - lastTriggerMs >= cooldownMs
                ) {
                    armed = true
                    outsidePoseStartedMs = 0L
                    poseStartedMs = 0L
                    movingUntilMs = 0L
                    movementBurstStartedMs = 0L
                    movementHits = 0
                    approachPrimedUntilMs = 0L
                    approachStartSimilarity = 1f
                }
            } else {
                outsidePoseStartedMs = 0L
            }
            lastSimilarity = similarity
            hasSimilarity = true
            return DetectionDebug(false, similarity, dynamic, armed)
        }

        val recentlyMoved = timeMs <= movingUntilMs
        val movementConfirmed = recentlyMoved && movementHits >= requiredMovementHits
        if (recentlyMoved) {
            val previous = if (hasSimilarity) lastSimilarity else similarity
            val candidateStart = min(previous, similarity)
            if (candidateStart <= approachStartSimilarityThreshold) {
                approachStartSimilarity =
                    if (timeMs > approachPrimedUntilMs) candidateStart
                    else min(approachStartSimilarity, candidateStart)
                approachPrimedUntilMs = timeMs + approachWindowMs
            }
        }

        val approachedMouth =
            timeMs <= approachPrimedUntilMs &&
            similarity - approachStartSimilarity >= minimumApproachRise
        val matchesPose = similarity >= similarityThreshold
        val cooledDown = timeMs - lastTriggerMs >= cooldownMs

        if (movementConfirmed && approachedMouth && matchesPose && cooledDown) {
            if (poseStartedMs == 0L) poseStartedMs = timeMs
            if (timeMs - poseStartedMs >= holdMs) {
                lastTriggerMs = timeMs
                poseStartedMs = 0L
                movingUntilMs = 0L
                movementBurstStartedMs = 0L
                movementHits = 0
                outsidePoseStartedMs = 0L
                approachPrimedUntilMs = 0L
                approachStartSimilarity = 1f
                armed = false
                lastSimilarity = similarity
                hasSimilarity = true
                return DetectionDebug(true, similarity, dynamic, armed)
            }
        } else {
            poseStartedMs = 0L
        }

        if (timeMs > movingUntilMs && timeMs > approachPrimedUntilMs) {
            movementHits = 0
            movementBurstStartedMs = 0L
            approachStartSimilarity = 1f
        }

        lastSimilarity = similarity
        hasSimilarity = true
        return DetectionDebug(false, similarity, dynamic, armed)
    }
}
