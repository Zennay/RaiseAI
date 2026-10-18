package nl.zennay.raiseai

internal object MonitoringServiceStartPolicy {
    fun tryStart(startAction: () -> Boolean): Boolean {
        return try {
            startAction()
        } catch (_: SecurityException) {
            false
        } catch (_: IllegalStateException) {
            false
        }
    }
}
