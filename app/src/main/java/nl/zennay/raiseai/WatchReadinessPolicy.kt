package nl.zennay.raiseai

data class WatchReadinessInputs(
    val calibrated: Boolean,
    val monitoringEnabled: Boolean,
    val handsFreeGrant: Boolean,
    val sessionGuardAccess: Boolean,
    val gatewayConfigured: Boolean,
    val sleepDndPauseEnabled: Boolean
)

data class WatchReadinessSummary(
    val headline: String,
    val lines: List<String>
) {
    fun asDisplayText(): String = (listOf(headline) + lines).joinToString("\n")
}

object WatchReadinessPolicy {
    fun summarize(input: WatchReadinessInputs): WatchReadinessSummary {
        val criticalReady = input.calibrated &&
            input.monitoringEnabled &&
            input.handsFreeGrant &&
            input.gatewayConfigured

        val lines = listOf(
            if (input.calibrated) "✓ Mouth pose calibrated" else "○ Calibrate mouth pose",
            if (input.monitoringEnabled) "✓ Raise-to-talk enabled" else "○ Enable raise-to-talk",
            if (input.handsFreeGrant) "✓ Hands-free launch granted" else "○ Grant hands-free launch",
            if (input.gatewayConfigured) "✓ Secure VPS gateway configured" else "○ Configure VPS gateway",
            if (input.sessionGuardAccess) "✓ Assistant session guard active" else "○ Session guard fallback: 30 sec",
            if (input.sleepDndPauseEnabled) "✓ Sleep/DND pause enabled" else "○ Sleep/DND pause is off"
        )

        return WatchReadinessSummary(
            headline = if (criticalReady) "✓ Raise AI ready" else "⚠ Setup needed",
            lines = lines
        )
    }
}
