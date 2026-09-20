package com.example.nika_business_app

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the optional P12 password encrypted with a key that lives in
 * Android Keystore. The plaintext password is never written to disk.
 */
object SecureBankSigningPasswordStore {
    private const val KEY_ALIAS = "nika_business_bank_signing_password_v1"
    private const val PREFS_NAME = "nika_business_bank_signing_secure"
    private const val PREF_IV = "password_iv"
    private const val PREF_DATA = "password_data"

    fun save(context: Context, password: String) {
        if (password.isEmpty()) {
            clear(context)
            return
        }
        requireModernAndroid()

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.doFinal(password.toByteArray(StandardCharsets.UTF_8))

        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString(PREF_DATA, Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .apply()
    }

    fun load(context: Context): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return null

        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val ivRaw = prefs.getString(PREF_IV, null) ?: return null
        val dataRaw = prefs.getString(PREF_DATA, null) ?: return null

        return try {
            val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            val key = keyStore.getKey(KEY_ALIAS, null) as? SecretKey ?: return null
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                GCMParameterSpec(128, Base64.decode(ivRaw, Base64.NO_WRAP)),
            )
            val plain = cipher.doFinal(Base64.decode(dataRaw, Base64.NO_WRAP))
            String(plain, StandardCharsets.UTF_8)
        } catch (_: Exception) {
            clear(context)
            null
        }
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(PREF_IV)
            .remove(PREF_DATA)
            .apply()
    }

    private fun getOrCreateKey(): SecretKey {
        requireModernAndroid()
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
    }

    private fun requireModernAndroid() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            throw IllegalStateException(
                "Безопасное сохранение пароля ЭЦП доступно с Android 6.0",
            )
        }
    }
}
