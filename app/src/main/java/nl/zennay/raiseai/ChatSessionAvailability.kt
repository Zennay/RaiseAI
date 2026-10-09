package nl.zennay.raiseai

/**
 * Tracks whether the cached ChatGPT Gecko session has completed a usable page load.
 *
 * Starting navigation must not make the cache reusable: the Activity may disappear while
 * navigation is still in flight, in which case the next lease must retry the initial load.
 */
internal class ChatSessionAvailability {
    var needsInitialLoad: Boolean = true
        private set

    fun reset() {
        needsInitialLoad = true
    }

    fun markNavigationStarted() {
        needsInitialLoad = true
    }

    fun markPageAvailable() {
        needsInitialLoad = false
    }

    fun markLoadFailed() {
        needsInitialLoad = true
    }
}
