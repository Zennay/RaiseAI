package nl.zennay.raiseai

internal data class ForegroundTransition(
    val packageName: String,
    val timestampMs: Long,
    val resumed: Boolean,
    val activityName: String = "",
    val packageWide: Boolean = false
)

internal object ForegroundActivityState {
    fun currentPackage(events: Sequence<ForegroundTransition>): String? {
        var currentPackage: String? = null
        val activeActivities = mutableMapOf<String, MutableSet<String>>()
        val packageWideForeground = mutableSetOf<String>()

        events.withIndex()
            .sortedWith(
                compareBy<IndexedValue<ForegroundTransition>> { it.value.timestampMs }
                    .thenBy { it.index }
            )
            .forEach { indexed ->
                val event = indexed.value
                val packageName = event.packageName
                if (packageName.isBlank()) return@forEach

                if (event.packageWide) {
                    if (event.resumed) {
                        packageWideForeground += packageName
                        currentPackage = packageName
                    } else {
                        packageWideForeground -= packageName
                        activeActivities.remove(packageName)
                        if (currentPackage == packageName) currentPackage = null
                    }
                    return@forEach
                }

                val activityName = event.activityName
                if (event.resumed) {
                    if (activityName.isNotBlank()) {
                        activeActivities
                            .getOrPut(packageName) { mutableSetOf() }
                            .add(activityName)
                    }
                    currentPackage = packageName
                    return@forEach
                }

                // An activity-scoped background event without an activity identity cannot
                // prove the whole package left foreground. Keep the current package
                // conservatively until a concrete activity/package transition says so.
                if (activityName.isBlank()) return@forEach

                val activeForPackage = activeActivities[packageName]
                activeForPackage?.remove(activityName)
                if (activeForPackage?.isEmpty() == true) {
                    activeActivities.remove(packageName)
                }

                if (
                    currentPackage == packageName &&
                    activeActivities[packageName].isNullOrEmpty() &&
                    packageName !in packageWideForeground
                ) {
                    currentPackage = null
                }
            }

        return currentPackage
    }
}
