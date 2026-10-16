package nl.zennay.raiseai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UsageAccessGateTest {
    private val allowed = 0
    private val ignored = 1
    private val errored = 2

    @Test fun grantedModeAllowsForegroundLookup() {
        assertTrue(UsageAccessGate.isAllowed(allowed) { allowed })
    }

    @Test fun ignoredModeUsesConservativeFallback() {
        assertFalse(UsageAccessGate.isAllowed(allowed) { ignored })
    }

    @Test fun deniedModeUsesConservativeFallback() {
        assertFalse(UsageAccessGate.isAllowed(allowed) { errored })
    }

    @Test fun missingAppOpsServiceUsesConservativeFallback() {
        assertFalse(UsageAccessGate.isAllowed(allowed) { null })
    }

    @Test fun securityExceptionUsesConservativeFallback() {
        assertFalse(UsageAccessGate.isAllowed(allowed) {
            throw SecurityException("usage permission unavailable")
        })
    }

    @Test fun nullServiceLookupExceptionUsesConservativeFallback() {
        assertFalse(UsageAccessGate.isAllowed(allowed) {
            throw NullPointerException("broken OEM appops")
        })
    }

    @Test fun incorrectPreferencesOrPlatformStateDoNotCrash() {
        assertFalse(UsageAccessGate.isAllowed(allowed) {
            throw IllegalStateException("AppOps lookup failed")
        })
    }

    @Test(expected = AssertionError::class)
    fun fatalErrorsAreNotHidden() {
        UsageAccessGate.isAllowed(allowed) {
            throw AssertionError("fatal")
        }
    }
}
