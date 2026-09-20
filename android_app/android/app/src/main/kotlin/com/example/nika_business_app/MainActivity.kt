package com.example.nika_business_app

import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.content.ActivityNotFoundException
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    private val updateChannel = "com.nikabusiness.app/updates"
    private val scannerChannel = "com.nikabusiness.app/scanner"
    private val signingChannel = "com.nikabusiness.app/signing"
    private val p12RequestCode = 9301
    private var pendingSigningResult: MethodChannel.Result? = null
    private var pendingSigningPayload: String? = null
    private var pendingSigningPassword: CharArray? = null
    private var pendingSigningMethod: String? = null
    private var pendingSigningTimestampMs: Long? = null
    private var pendingSaveKey: Boolean = false
    private var updateDownloadId: Long = -1
    private var receiverRegistered = false
    private var scannerTone: ToneGenerator? = null

    private val downloadReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1)
            if (id != updateDownloadId) return
            val manager = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            val apkUri = manager.getUriForDownloadedFile(id) ?: return
            startActivity(Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(apkUri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            })
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val filter = IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(downloadReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(downloadReceiver, filter)
        }
        receiverRegistered = true
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, scannerChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "playBeep" -> {
                        try {
                            if (scannerTone == null) {
                                scannerTone = ToneGenerator(AudioManager.STREAM_ALARM, 90)
                            }
                            scannerTone?.stopTone()
                            scannerTone?.startTone(ToneGenerator.TONE_PROP_BEEP, 170)
                            result.success(null)
                        } catch (error: Exception) {
                            result.error("BEEP_FAILED", error.message, null)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, signingChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getSigningCapabilities" -> {
                        result.success(KalkanJwsSigner.capabilities())
                    }
                    "loadSavedP12Password" -> {
                        result.success(SecureSigningPasswordStore.load(this))
                    }
                    "saveP12Password" -> {
                        val password = call.argument<String>("password") ?: ""
                        try {
                            SecureSigningPasswordStore.save(this, password)
                            result.success(null)
                        } catch (error: Exception) {
                            result.error(
                                "PASSWORD_SAVE_FAILED",
                                error.message ?: "Не удалось сохранить пароль ЭЦП",
                                null,
                            )
                        }
                    }
                    "clearSavedP12Password" -> {
                        SecureSigningPasswordStore.clear(this)
                        result.success(null)
                    }
                    "getSavedP12KeyInfo" -> {
                        result.success(
                            mapOf(
                                "hasKey" to SecureSigningKeyStore.hasSavedKey(this),
                                "name" to SecureSigningKeyStore.displayName(this),
                                "hasPassword" to !SecureSigningPasswordStore.load(this).isNullOrEmpty(),
                            )
                        )
                    }
                    "clearSavedP12Key" -> {
                        SecureSigningKeyStore.clear(this)
                        SecureSigningPasswordStore.clear(this)
                        result.success(null)
                    }
                    "loadSavedBankP12Password" -> {
                        result.success(SecureBankSigningPasswordStore.load(this))
                    }
                    "saveBankP12Password" -> {
                        val password = call.argument<String>("password") ?: ""
                        try {
                            SecureBankSigningPasswordStore.save(this, password)
                            result.success(null)
                        } catch (error: Exception) {
                            result.error(
                                "BANK_PASSWORD_SAVE_FAILED",
                                error.message ?: "Не удалось сохранить пароль банковской ЭЦП",
                                null,
                            )
                        }
                    }
                    "clearSavedBankP12Password" -> {
                        SecureBankSigningPasswordStore.clear(this)
                        result.success(null)
                    }
                    "getSavedBankP12KeyInfo" -> {
                        result.success(
                            mapOf(
                                "hasKey" to SecureBankSigningKeyStore.hasSavedKey(this),
                                "name" to SecureBankSigningKeyStore.displayName(this),
                                "hasPassword" to !SecureBankSigningPasswordStore.load(this).isNullOrEmpty(),
                            )
                        )
                    }
                    "clearSavedBankP12Key" -> {
                        SecureBankSigningKeyStore.clear(this)
                        SecureBankSigningPasswordStore.clear(this)
                        result.success(null)
                    }
                    "loadSavedEsfAuth" -> {
                        result.success(SecureEsfAuthStore.load(this))
                    }
                    "saveEsfAuth" -> {
                        val iin = call.argument<String>("iin") ?: ""
                        val password = call.argument<String>("password") ?: ""
                        val profileType = call.argument<String>("profile_type") ?: "ADMIN_ENTERPRISE"
                        try {
                            SecureEsfAuthStore.save(
                                context = this,
                                iin = iin,
                                password = password,
                                profileType = profileType,
                            )
                            result.success(null)
                        } catch (error: Exception) {
                            result.error(
                                "ESF_AUTH_SAVE_FAILED",
                                error.message ?: "Не удалось сохранить пароль ИС ЭСФ",
                                null,
                            )
                        }
                    }
                    "clearSavedEsfAuth" -> {
                        SecureEsfAuthStore.clear(this)
                        result.success(null)
                    }
                    "signAlatauJwsWithSavedP12" -> {
                        val payload = call.argument<String>("payload") ?: ""
                        val signingTimestampMs =
                            call.argument<Number>("signingTimestampMs")?.toLong()
                        startSavedP12Signing(
                            "signAlatauJwsWithP12",
                            payload,
                            signingTimestampMs,
                            result,
                        )
                    }
                    "signEsfRawWithSavedP12" -> {
                        val payload = call.argument<String>("payload") ?: ""
                        startSavedP12Signing("signEsfRawWithP12", payload, null, result)
                    }
                    "signEsfXmlWithSavedP12" -> {
                        val payload = call.argument<String>("payload") ?: ""
                        startSavedP12Signing("signEsfXmlWithP12", payload, null, result)
                    }
                    "signAlatauJwsWithP12",
                    "signEsfRawWithP12",
                    "signEsfXmlWithP12" -> {
                        val payload = call.argument<String>("payload") ?: ""
                        val password = call.argument<String>("password") ?: ""
                        val saveKey = call.argument<Boolean>("saveKey") ?: false
                        val signingTimestampMs =
                            call.argument<Number>("signingTimestampMs")?.toLong()
                        startP12Signing(
                            call.method,
                            payload,
                            password,
                            saveKey,
                            signingTimestampMs,
                            result,
                        )
                    }
                    else -> result.notImplemented()
                }
            }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, updateChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getVersionName" -> result.success(
                        packageManager.getPackageInfo(packageName, 0).versionName
                    )
                    "downloadAndInstall" -> {
                        val url = call.argument<String>("url")
                        val version = call.argument<String>("version") ?: "latest"
                        if (url.isNullOrBlank()) {
                            result.error("INVALID_URL", "Не указан адрес обновления", null)
                        } else if (
                            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                            !packageManager.canRequestPackageInstalls()
                        ) {
                            startActivity(Intent(
                                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:$packageName")
                            ))
                            result.success("permission_required")
                        } else {
                            startUpdateDownload(url, version)
                            result.success("downloading")
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun startP12Signing(
        method: String,
        payload: String,
        password: String,
        saveKey: Boolean,
        signingTimestampMs: Long?,
        result: MethodChannel.Result,
    ) {
        val capabilities = KalkanJwsSigner.capabilities()
        val capabilityKey = when (method) {
            "signAlatauJwsWithP12" -> "readyForAlatau"
            "signEsfRawWithP12" -> "readyForEsfRaw"
            "signEsfXmlWithP12" -> "readyForEsfXml"
            else -> null
        }
        if (capabilityKey != null && capabilities[capabilityKey] != true) {
            val message = if (method == "signEsfXmlWithP12") {
                "В этой сборке Nika Business нет полного KalkanCrypt XMLDSig SDK НУЦ РК."
            } else {
                "В этой сборке Nika Business нет KalkanCrypt НУЦ РК."
            }
            result.error("KALKAN_NOT_INSTALLED", message, capabilities)
            return
        }

        if (payload.isBlank()) {
            result.error("EMPTY_PAYLOAD", "Нет данных для подписи", null)
            return
        }
        if (password.isEmpty()) {
            result.error("EMPTY_PASSWORD", "Введите пароль ЭЦП", null)
            return
        }
        if (pendingSigningResult != null) {
            result.error("SIGNING_BUSY", "Уже открыт выбор ЭЦП", null)
            return
        }

        pendingSigningResult = result
        pendingSigningPayload = payload
        pendingSigningPassword = password.toCharArray()
        pendingSigningMethod = method
        pendingSigningTimestampMs = signingTimestampMs
        pendingSaveKey = saveKey

        try {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(
                    Intent.EXTRA_MIME_TYPES,
                    arrayOf(
                        "application/x-pkcs12",
                        "application/pkcs12",
                        "application/octet-stream",
                    )
                )
            }
            startActivityForResult(intent, p12RequestCode)
        } catch (error: ActivityNotFoundException) {
            clearPendingSigning()
            result.error("FILE_PICKER_UNAVAILABLE", "На телефоне нет приложения для выбора файла ЭЦП", null)
        } catch (error: Exception) {
            clearPendingSigning()
            result.error("FILE_PICKER_FAILED", error.message ?: "Не удалось открыть выбор ЭЦП", null)
        }
    }


    private fun startSavedP12Signing(
        method: String,
        payload: String,
        signingTimestampMs: Long?,
        result: MethodChannel.Result,
    ) {
        if (payload.isBlank()) {
            result.error("EMPTY_PAYLOAD", "Нет данных для подписи", null)
            return
        }
        val isBankSigning = method == "signAlatauJwsWithP12"
        val keyUri = if (isBankSigning) {
            SecureBankSigningKeyStore.savedUri(this)
        } else {
            SecureSigningKeyStore.savedUri(this)
        }
        val password = if (isBankSigning) {
            SecureBankSigningPasswordStore.load(this)
        } else {
            SecureSigningPasswordStore.load(this)
        }
        if (keyUri == null || password.isNullOrEmpty()) {
            result.error(
                "SAVED_KEY_UNAVAILABLE",
                "Сначала сохраните ключ и пароль ЭЦП на этом телефоне",
                null,
            )
            return
        }

        val authenticators =
            BiometricManager.Authenticators.BIOMETRIC_STRONG or
                BiometricManager.Authenticators.DEVICE_CREDENTIAL
        val biometricManager = BiometricManager.from(this)
        if (biometricManager.canAuthenticate(authenticators) != BiometricManager.BIOMETRIC_SUCCESS) {
            result.error(
                "BIOMETRIC_UNAVAILABLE",
                "На телефоне не настроен отпечаток, биометрия или блокировка экрана",
                null,
            )
            return
        }

        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(
                    authResult: BiometricPrompt.AuthenticationResult,
                ) {
                    try {
                        val response = when (method) {
                            "signAlatauJwsWithP12" -> KalkanJwsSigner.signAlatauJws(
                                context = this@MainActivity,
                                keyUri = keyUri,
                                passwordChars = password.toCharArray(),
                                payload = payload,
                                signingTimestampMs = signingTimestampMs,
                            )
                            "signEsfRawWithP12" -> KalkanJwsSigner.signEsfRaw(
                                context = this@MainActivity,
                                keyUri = keyUri,
                                passwordChars = password.toCharArray(),
                                payload = payload,
                            )
                            "signEsfXmlWithP12" -> KalkanJwsSigner.signEsfXml(
                                context = this@MainActivity,
                                keyUri = keyUri,
                                passwordChars = password.toCharArray(),
                                payload = payload,
                            )
                            else -> throw KalkanJwsSigner.SigningException(
                                "UNKNOWN_SIGN_METHOD",
                                "Неизвестный режим подписи",
                            )
                        }
                        result.success(response)
                    } catch (error: KalkanJwsSigner.SigningException) {
                        result.error(error.code, error.message, null)
                    } catch (error: Exception) {
                        result.error(
                            "SIGN_FAILED",
                            error.message ?: "Не удалось подписать платёж",
                            null,
                        )
                    }
                }

                override fun onAuthenticationError(
                    errorCode: Int,
                    errString: CharSequence,
                ) {
                    result.error("BIOMETRIC_CANCELLED", errString.toString(), null)
                }
            },
        )

        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Подтвердите подпись")
                .setSubtitle("Nika Business использует сохранённую ЭЦП")
                .setAllowedAuthenticators(authenticators)
                .build()
        )
    }


    private fun startUpdateDownload(url: String, version: String) {
        val request = DownloadManager.Request(Uri.parse(url)).apply {
            setTitle("Nika Business $version")
            setDescription("Скачивание обновления")
            setMimeType("application/vnd.android.package-archive")
            setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
            )
            setDestinationInExternalFilesDir(
                this@MainActivity,
                Environment.DIRECTORY_DOWNLOADS,
                "NikaBusiness-$version.apk"
            )
        }
        val manager = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        updateDownloadId = manager.enqueue(request)
    }

    @Deprecated("Deprecated in Android")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != p12RequestCode) {
            super.onActivityResult(requestCode, resultCode, data)
            return
        }

        val callback = pendingSigningResult
        val payload = pendingSigningPayload
        val password = pendingSigningPassword
        val method = pendingSigningMethod
        val signingTimestampMs = pendingSigningTimestampMs

        if (callback == null || payload == null || password == null || method == null) {
            clearPendingSigning()
            return
        }

        if (resultCode != RESULT_OK || data?.data == null) {
            clearPendingSigning()
            callback.error("USER_CANCELLED", "Выбор ЭЦП отменён", null)
            return
        }

        val uri = data.data!!
        try {
            val response = when (method) {
                "signAlatauJwsWithP12" -> KalkanJwsSigner.signAlatauJws(
                    context = this,
                    keyUri = uri,
                    passwordChars = password,
                    payload = payload,
                    signingTimestampMs = signingTimestampMs,
                )
                "signEsfRawWithP12" -> KalkanJwsSigner.signEsfRaw(
                    context = this,
                    keyUri = uri,
                    passwordChars = password,
                    payload = payload,
                )
                "signEsfXmlWithP12" -> KalkanJwsSigner.signEsfXml(
                    context = this,
                    keyUri = uri,
                    passwordChars = password,
                    payload = payload,
                )
                else -> throw KalkanJwsSigner.SigningException(
                    "UNKNOWN_SIGN_METHOD",
                    "Неизвестный режим мобильной подписи",
                )
            }
            if (pendingSaveKey) {
                try {
                    if (method == "signAlatauJwsWithP12") {
                        SecureBankSigningKeyStore.saveFromUri(this, uri)
                    } else {
                        SecureSigningKeyStore.saveFromUri(this, uri)
                    }
                } catch (error: Exception) {
                    clearPendingSigning()
                    callback.error(
                        "KEY_SAVE_FAILED",
                        error.message ?: "Не удалось сохранить файл ЭЦП",
                        null,
                    )
                    return
                }
            }
            clearPendingSigning()
            callback.success(response)
        } catch (error: KalkanJwsSigner.SigningException) {
            clearPendingSigning()
            callback.error(error.code, error.message, null)
        } catch (error: Exception) {
            clearPendingSigning()
            callback.error("SIGN_FAILED", error.message ?: "Не удалось подписать платёж", null)
        }
    }

    private fun clearPendingSigning() {
        pendingSigningPassword?.fill('\u0000')
        pendingSigningPassword = null
        pendingSigningPayload = null
        pendingSigningMethod = null
        pendingSigningTimestampMs = null
        pendingSaveKey = false
        pendingSigningResult = null
    }

    override fun onDestroy() {
        if (receiverRegistered) unregisterReceiver(downloadReceiver)
        receiverRegistered = false
        scannerTone?.release()
        scannerTone = null
        pendingSigningResult?.error("ACTIVITY_DESTROYED", "Окно приложения закрыто", null)
        clearPendingSigning()
        super.onDestroy()
    }
}
