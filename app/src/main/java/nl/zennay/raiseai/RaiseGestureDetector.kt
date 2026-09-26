package nl.zennay.raiseai

import kotlin.math.sqrt

data class DetectionDebug(
    val triggered: Boolean,
    val similarity: Float,
    val dynamicAcceleration: Float,
    val armed: Boolean
)

/**
 * Raise-to-mouth detector with explicit re-arming.
 *
 * After a trigger, the detector is disarmed. It will not trigger again until the wrist has
 * clearly left the calibrated mouth pose for a short period. This prevents the assistant from being
 * reopened repeatedly while the user is still talking or keeps the watch near their mouth.
 */
class RaiseGestureDetector {
    private var gravityX = 0f
    private var gravityY = 0f
    private var gravityZ = 9.81f
    private var initialized = false

    private var movingUntilMs = 0L
    private var poseStartedMs = 0L
    private var outsidePoseStartedMs = 0L
    private var lastTriggerMs = Long.MIN_VALUE / 2
    private var armed = true

    var similarityThreshold = 0.965f
    var rearmSimilarityThreshold = 0.90f
    var movementThreshold = 1.25f
    var holdMs = 180L
    var movementWindowMs = 1_250L
    var cooldownMs = 3_000L
    var rearmHoldMs = 550L

    fun onAccelerometer(
        x: Float,
        y: Float,
        z: Float,
        timeMs: Long,
        mouthPose: MouthPose?
    ): DetectionDebug {
        if (!initialized) {
            gravityX = x
            gravityY = y
            gravityZ = z
            initialized = true
        }

        val alpha = 0.86f
        gravityX = alpha * gravityX + (1f - alpha) * x
        gravityY = alpha * gravityY + (1f - alpha) * y
        gravityZ = alpha * gravityZ + (1f - alpha) * z

        val dx = x - gravityX
        val dy = y - gravityY
        val dz = z - gravityZ
        val dynamic = sqrt(dx * dx + dy * dy + dz * dz)
        if (dynamic >= movementThreshold) {
            movingUntilMs = timeMs + movementWindowMs
        }

        if (mouthPose == null) {
            poseStartedMs = 0L
            return DetectionDebug(false, 0f, dynamic, armed)
        }

        val gravityLength = sqrt(
            gravityX * gravityX + gravityY * gravityY + gravityZ * gravityZ
        ).coerceAtLeast(0.001f)

        val nx = gravityX / gravityLength
        val ny = gravityY / gravityLength
        val nz = gravityZ / gravityLength
        val similarity = nx * mouthPose.x + ny * mouthPose.y + nz * mouthPose.z

        if (!armed) {
            val clearlyAwayFromMouth = similarity < rearmSimilarityThreshold
            if (clearlyAwayFromMouth) {
                if (outsidePoseStartedMs == 0L) outsidePoseStartedMs = timeMs
                val awayLongEnough = timeMs - outsidePoseStartedMs >= rearmHoldMs
                val cooldownDone = timeMs - lastTriggerMs >= cooldownMs
                if (awayLongEnough && cooldownDone) {
                    armed = true
                    outsidePoseStartedMs = 0L
                    poseStartedMs = 0L
                    movingUntilMs = 0L
                }
            } else {
                outsidePoseStartedMs = 0L
            }
            return DetectionDebug(false, similarity, dynamic, armed)
        }

        val recentlyMoved = timeMs <= movingUntilMs
        val matchesPose = similarity >= similarityThreshold
        val cooledDown = timeMs - lastTriggerMs >= cooldownMs

        if (recentlyMoved && matchesPose && cooledDown) {
            if (poseStartedMs == 0L) poseStartedMs = timeMs
            if (timeMs - poseStartedMs >= holdMs) {
                lastTriggerMs = timeMs
                poseStartedMs = 0L
                movingUntilMs = 0L
                outsidePoseStartedMs = 0L
                armed = false
                return DetectionDebug(true, similarity, dynamic, armed)
            }
        } else {
            poseStartedMs = 0L
        }

        return DetectionDebug(false, similarity, dynamic, armed)
    }
}
