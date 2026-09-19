package com.example.nika_business_app

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File

/**
 * Keeps an optional user-selected PKCS#12 key inside the private app sandbox.
 *
 * The original file is copied once after a successful signature. It never
 * leaves the device and is not uploaded to Nika servers.
 */
object SecureSigningKeyStore {
    private const val DIRECTORY = "signing"
    private const val FILE_NAME = "saved_signing_key.p12"
    private const val PREFS_NAME = "nika_business_signing_key"
    private const val PREF_DISPLAY_NAME = "display_name"

    fun hasSavedKey(context: Context): Boolean = savedFile(context).let {
        it.exists() && it.length() > 0
    }

    fun savedUri(context: Context): Uri? {
        val file = savedFile(context)
        return if (file.exists() && file.length() > 0) Uri.fromFile(file) else null
    }

    fun displayName(context: Context): String? {
        if (!hasSavedKey(context)) return null
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(PREF_DISPLAY_NAME, null)
            ?: "Сохранённая ЭЦП"
    }

    fun saveFromUri(context: Context, source: Uri): String {
        val directory = File(context.filesDir, DIRECTORY)
        if (!directory.exists() && !directory.mkdirs()) {
            throw IllegalStateException("Не удалось создать защищённое хранилище ЭЦП")
        }

        val destination = savedFile(context)
        val input = context.contentResolver.openInputStream(source)
            ?: throw IllegalStateException("Не удалось открыть выбранный файл ЭЦП")
        input.use { sourceStream ->
            destination.outputStream().use { target ->
                sourceStream.copyTo(target)
            }
        }

        if (!destination.exists() || destination.length() == 0L) {
            clear(context)
            throw IllegalStateException("Не удалось сохранить файл ЭЦП на телефоне")
        }

        val name = queryDisplayName(context, source) ?: "Сохранённая ЭЦП"
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_DISPLAY_NAME, name)
            .apply()
        return name
    }

    fun clear(context: Context) {
        runCatching { savedFile(context).delete() }
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .clear()
            .apply()
    }

    private fun savedFile(context: Context): File =
        File(File(context.filesDir, DIRECTORY), FILE_NAME)

    private fun queryDisplayName(context: Context, uri: Uri): String? {
        return runCatching {
            context.contentResolver.query(
                uri,
                arrayOf(OpenableColumns.DISPLAY_NAME),
                null,
                null,
                null,
            )?.use { cursor ->
                if (!cursor.moveToFirst()) return@use null
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index < 0) null else cursor.getString(index)
            }
        }.getOrNull()
    }
}
