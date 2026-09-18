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
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val updateChannel = "com.nikabusiness.app/updates"
    private val scannerChannel = "com.nikabusiness.app/scanner"
    private val signingChannel = "com.nikabusiness.app/signing"
    private val p12RequestCode = 9301
    private var pendingSigningResult: MethodChannel.Result? = null
    private var pendingSigningPayload: String? = null
    private var pendingSigningPassword: CharArray? = null
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
                    "signAlatauJwsWithP12" -> {
                        val payload = call.argument<String>("payload") ?: ""
                        val password = call.argument<String>("password") ?: ""
                        if (payload.isBlank()) {
                            result.error("EMPTY_PAYLOAD", "Нет данных платежа для подписи", null)
                            return@setMethodCallHandler
                        }
                        if (password.isEmpty()) {
                            result.error("EMPTY_PASSWORD", "Введите пароль ЭЦП", null)
                            return@setMethodCallHandler
                        }
                        if (pendingSigningResult != null) {
                            result.error("SIGNING_BUSY", "Уже открыт выбор ЭЦП", null)
                            return@setMethodCallHandler
                        }

                        pendingSigningResult = result
                        pendingSigningPayload = payload
                        pendingSigningPassword = password.toCharArray()

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

        if (callback == null || payload == null || password == null) {
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
            val response = KalkanJwsSigner.signAlatauJws(
                context = this,
                keyUri = uri,
                password = String(password),
                payload = payload,
            )
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
