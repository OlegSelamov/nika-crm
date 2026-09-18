import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../services/api_service.dart';
import '../services/mobile_p12_signer.dart';
import '../theme/app_theme.dart';

class WebModuleScreen extends StatefulWidget {
  final String title;
  final String path;

  const WebModuleScreen({super.key, required this.title, required this.path});

  @override
  State<WebModuleScreen> createState() => _WebModuleScreenState();
}

class _WebModuleScreenState extends State<WebModuleScreen> {
  late final WebViewController controller;
  int progress = 0;
  String? error;
  bool ready = false;

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    final rawCookie = ApiService.sessionCookie;
    if (rawCookie != null && rawCookie.contains('=')) {
      final separator = rawCookie.indexOf('=');
      await WebViewCookieManager().setCookie(
        WebViewCookie(
          name: rawCookie.substring(0, separator),
          value: rawCookie.substring(separator + 1),
          domain: 'www.nikabusiness.com',
          path: '/',
        ),
      );
    }

    controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel(
        'NikaMobileSigner',
        onMessageReceived: (message) => _handleMobileSignerMessage(message.message),
      )
      ..setBackgroundColor(AppColors.background)
      ..setUserAgent('NikaBusinessMobile/2.0')
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (value) {
            if (mounted) setState(() => progress = value);
          },
          onPageFinished: (_) {
            if (mounted) setState(() => progress = 100);
          },
          onWebResourceError: (webError) {
            if (webError.isForMainFrame == true && mounted) {
              setState(() => error = webError.description);
            }
          },
          onNavigationRequest: (request) {
            final host = Uri.tryParse(request.url)?.host.toLowerCase() ?? '';
            if (host == 'nikabusiness.com' || host.endsWith('.nikabusiness.com')) {
              return NavigationDecision.navigate;
            }
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Внешняя ссылка заблокирована в рабочем режиме')),
              );
            }
            return NavigationDecision.prevent;
          },
        ),
      )
      ..loadRequest(Uri.parse('${ApiService.baseUrl}${widget.path}'));

    if (mounted) setState(() => ready = true);
  }

  Future<void> _handleMobileSignerMessage(String rawMessage) async {
    if (!widget.path.startsWith('/banks')) return;

    String requestId = '';
    try {
      final decoded = jsonDecode(rawMessage);
      if (decoded is! Map) return;
      final message = Map<String, dynamic>.from(decoded);
      if (message['action'] != 'signAlatauJws') return;

      requestId = (message['requestId'] ?? '').toString();
      final payload = (message['payload'] ?? '').toString();
      final password = (message['password'] ?? '').toString();

      if (requestId.isEmpty || payload.isEmpty) {
        await _sendSignerResult(
          requestId,
          const {
            'success': false,
            'code': 'INVALID_REQUEST',
            'error': 'Нет данных платежа для подписи',
          },
        );
        return;
      }

      final result = await MobileP12Signer.signAlatauJws(
        payload: payload,
        password: password,
      );

      await _sendSignerResult(
        requestId,
        {
          'success': true,
          ...result,
        },
      );
    } on PlatformException catch (error) {
      await _sendSignerResult(
        requestId,
        {
          'success': false,
          'code': error.code,
          'error': error.message ?? 'Не удалось подписать платёж',
        },
      );
    } catch (error) {
      await _sendSignerResult(
        requestId,
        {
          'success': false,
          'code': 'MOBILE_SIGN_FAILED',
          'error': error.toString(),
        },
      );
    }
  }

  Future<void> _sendSignerResult(
    String requestId,
    Map<String, dynamic> result,
  ) async {
    if (!ready || requestId.isEmpty) return;
    final requestJson = jsonEncode(requestId);
    final resultJson = jsonEncode(result);
    await controller.runJavaScript(
      'window.NikaMobileSignerResult && '
      'window.NikaMobileSignerResult($requestJson, $resultJson);',
    );
  }

  Future<bool> _back() async {
    if (ready && await controller.canGoBack()) {
      await controller.goBack();
      return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: _back,
      child: Scaffold(
        appBar: AppBar(
          title: Text(widget.title),
          actions: [
            IconButton(
              tooltip: 'Назад на странице',
              onPressed: !ready
                  ? null
                  : () async {
                      if (await controller.canGoBack()) await controller.goBack();
                    },
              icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 19),
            ),
            IconButton(
              tooltip: 'Обновить',
              onPressed: !ready ? null : controller.reload,
              icon: const Icon(Icons.refresh_rounded),
            ),
          ],
          bottom: progress < 100
              ? PreferredSize(
                  preferredSize: const Size.fromHeight(2),
                  child: LinearProgressIndicator(value: progress / 100, minHeight: 2),
                )
              : null,
        ),
        body: error != null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.cloud_off_rounded, color: AppColors.muted, size: 48),
                      const SizedBox(height: 14),
                      const Text('Страница не загрузилась', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 7),
                      Text(error!, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.muted)),
                      const SizedBox(height: 18),
                      ElevatedButton.icon(
                        onPressed: () {
                          setState(() => error = null);
                          controller.reload();
                        },
                        icon: const Icon(Icons.refresh_rounded),
                        label: const Text('Повторить'),
                      ),
                    ],
                  ),
                ),
              )
            : ready
                ? WebViewWidget(controller: controller)
                : const Center(child: CircularProgressIndicator()),
      ),
    );
  }
}
