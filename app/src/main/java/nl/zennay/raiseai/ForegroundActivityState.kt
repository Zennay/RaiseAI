package nl.zennay.raiseai

internal data class ForegroundTransition(
    val packageName: String,
    val timestampMs: Long,
    val resumed: Boolean
)

internal object ForegroundActivityState {
    fun currentPackage(events: Sequence<ForegroundTransition>): String? {
        var currentPackage: String? = null

        events.withIndex()
            .sortedWith(
                compareBy<IndexedValue<ForegroundTransition>> { it.value.timestampMs }
                    .thenBy { it.index }
            )
            .forEach { indexed ->
                val event = indexed.value
                if (event.packageName.isBlank()) return@forEach

                if (event.resumed) {
                    currentPackage = event.packageName
                } else if (currentPackage == event.packageName) {
                    currentPackage = null
                }
            }

        return currentPackage
    }
}
