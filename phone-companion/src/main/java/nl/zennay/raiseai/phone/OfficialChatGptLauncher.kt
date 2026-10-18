package nl.zennay.raiseai.phone

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager

/**
 * Phone foreground-only consent action; does not enter Voice, capture audio or bridge Watch data.
 * Requires an independently trusted publisher signing-certificate fingerprint typed by the user.
 */
internal class OfficialChatGptLauncher(private val activity: Activity) {
    internal enum class Result {
        OPENED_OFFICIAL_APP,
        VERIFIED_OFFICIAL_APP,
        MISSING_APP,
        SIGNER_MISMATCH_OR_UNVERIFIED,
        LAUNCHER_UNAVAILABLE,
        LAUNCH_FAILED
    }

    /** Separate verification lets a fresh user-approved Watch request be checked *before* launch. */
    fun verifyInstalledPublisher(expectedSignerSha256: String): Result {
        val pm = activity.packageManager
        val packageInfo = try {
            @Suppress("DEPRECATION")
            pm.getPackageInfo(
                OfficialAppCertificatePolicy.PACKAGE,
                PackageManager.GET_SIGNING_CERTIFICATES
            )
        } catch (_: PackageManager.NameNotFoundException) {
            return Result.MISSING_APP
        } catch (_: RuntimeException) {
            return Result.SIGNER_MISMATCH_OR_UNVERIFIED
        }
        val signerInfo = packageInfo.signingInfo ?: return Result.SIGNER_MISMATCH_OR_UNVERIFIED
        val certs = try {
            if (signerInfo.hasMultipleSigners()) return Result.SIGNER_MISMATCH_OR_UNVERIFIED
            signerInfo.apkContentsSigners?.map { it.toByteArray() }
        } catch (_: RuntimeException) {
            return Result.SIGNER_MISMATCH_OR_UNVERIFIED
        }
        if (!OfficialAppCertificatePolicy.matches(expectedSignerSha256, certs)) {
            return Result.SIGNER_MISMATCH_OR_UNVERIFIED
        }
        return Result.VERIFIED_OFFICIAL_APP
    }

    fun launchOnExplicitButtonTap(expectedSignerSha256: String): Result {
        // Repeat signer verification at the actual launch boundary: previous validation
        // alone is not proof the installed package remained unchanged.
        val attestation = verifyInstalledPublisher(expectedSignerSha256)
        if (attestation != Result.VERIFIED_OFFICIAL_APP) return attestation
        val pm = activity.packageManager

        // This is only a public foreground launcher, never a private ChatGPT Voice intent.
        val launchIntent = try {
            pm.getLaunchIntentForPackage(OfficialAppCertificatePolicy.PACKAGE)
        } catch (_: RuntimeException) {
            null
        } ?: return Result.LAUNCHER_UNAVAILABLE
        if (launchIntent.component?.packageName != OfficialAppCertificatePolicy.PACKAGE ||
            launchIntent.action != Intent.ACTION_MAIN ||
            launchIntent.categories?.contains(Intent.CATEGORY_LAUNCHER) != true
        ) return Result.LAUNCHER_UNAVAILABLE

        return try {
            activity.startActivity(launchIntent)
            Result.OPENED_OFFICIAL_APP
        } catch (_: RuntimeException) {
            Result.LAUNCH_FAILED
        }
    }
}
