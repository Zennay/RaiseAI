package nl.zennay.raiseai

import java.io.File
import java.io.FileOutputStream
import java.io.IOException

internal object EvidenceFileStore {
    fun replace(
        destination: File,
        serialized: String,
        rename: (File, File) -> Boolean = { source, target -> source.renameTo(target) }
    ) {
        val directory = destination.parentFile
            ?: throw IOException("Evidence destination has no parent directory")
        val temporary = File(directory, "${destination.name}.tmp")
        val backup = File(directory, "${destination.name}.bak")

        if (temporary.exists() && !temporary.delete()) {
            throw IOException("Could not clear stale evidence temp file")
        }

        if (backup.exists()) {
            if (!destination.exists()) {
                if (!rename(backup, destination)) {
                    throw IOException("Could not restore stale evidence backup")
                }
            } else if (!backup.delete()) {
                throw IOException("Could not clear stale evidence backup")
            }
        }

        FileOutputStream(temporary).use { stream ->
            stream.write(serialized.toByteArray(Charsets.UTF_8))
            stream.fd.sync()
        }

        val hadDestination = destination.exists()
        if (hadDestination && !rename(destination, backup)) {
            temporary.delete()
            throw IOException("Could not stage previous evidence for replacement")
        }

        if (!rename(temporary, destination)) {
            temporary.delete()
            if (hadDestination && backup.exists() && !rename(backup, destination)) {
                throw IOException("Evidence replacement failed and previous evidence could not be restored")
            }
            throw IOException("Could not replace evidence file")
        }

        if (backup.exists()) {
            backup.delete()
        }
    }
}
