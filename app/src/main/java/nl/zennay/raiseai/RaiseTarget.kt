package nl.zennay.raiseai

enum class RaiseTarget(
    val storageValue: String,
    val displayName: String
) {
    GEMINI("gemini", "Gemini"),
    NATIVE("native", "Native Raise AI");

    companion object {
        fun fromStored(value: String?): RaiseTarget =
            entries.firstOrNull { it.storageValue == value } ?: GEMINI
    }
}
