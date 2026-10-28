import 'dart:convert';
import 'dart:typed_data';

import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/mobile_p12_signer.dart';

// Deliberately contains no taxpayer/company data and is not an official
// ISNA service request. Never send this sample to Smart Bridge.
String buildIsnaSignatureDemoXml({String? nonce}) {
  final id = nonce ?? DateTime.now().toUtc().microsecondsSinceEpoch.toString();
  return '<?xml version="1.0" encoding="UTF-8"?>'
      '<NikaIsnaTest xmlns="urn:nikabusiness:offline-signature-test:1">'
      '<Purpose>Local XML signature compatibility check only</Purpose>'
      '<Nonce>' + id + '</Nonce>'
      '<Submission>false</Submission>'
      '</NikaIsnaTest>';
}

class IsnaTestPanel extends StatefulWidget {
  const IsnaTestPanel({super.key});

  @override
  State<IsnaTestPanel> createState() => _IsnaTestPanelState();
}

class _IsnaTestPanelState extends State<IsnaTestPanel> {
  bool busy = false;
  String status = 'Готово к проверке. Ни одна декларация не отправлялась.';
  String? signedXml;

  Future<void> _check() async {
    if (busy) return;
    setState(() {
      busy = true;
      status = 'Проверяем TCP с TEST VPS. SOAP и ФНО не отправляются…';
    });
    try {
      final response = await ApiService.isnaTestDiagnostics();
      if (!mounted) return;
      final tcpOk = response['tcpOk'] == true;
      setState(() {
        status = [
          'Источник: TEST VPS',
          'TCP: ' + (tcpOk ? 'соединение установлено' : 'недоступно с TEST VPS'),
          'Адрес: ' + (response['endpoint'] ?? 'не задан').toString(),
          'senderId: ' + (response['senderConfigured'] == true ? 'указан' : 'не настроен'),
          'serviceId: ' +
              (response['serviceIdConfigured'] == true
                  ? 'указан (не подтверждён)'
                  : 'только значение по умолчанию'),
          'Транспортная подпись: ' +
              (response['transportSignerConfigured'] == true
                  ? 'настроена (не проверена)'
                  : 'пока не настроена'),
          (response['note'] ?? '').toString(),
          'SOAP-запросы не отправлялись.',
        ].join('\n');
      });
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Ошибка проверки: ' + error.toString() +
            '\nSOAP-запросы не отправлялись.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _sign() async {
    if (busy) return;
    // Use the existing *native* Kotlin KalkanCrypt implementation, not a
    // WebView, browser JS or NCALayer. Only sign an inert sample locally.
    final xml = buildIsnaSignatureDemoXml();
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _NativeIsnaSignDialog(xml: xml),
    );
    if (result == null || !mounted) return;
    final value = (result['signedXml'] ?? '').toString();
    if (!RegExp(r'<(?:[A-Za-z0-9_]+:)?Signature(?:\s|>)').hasMatch(value)) {
      setState(() => status = 'Криптомодуль не вернул элемент XML Signature.');
      return;
    }
    setState(() {
      signedXml = value;
      status = 'Пробный XML подписан через нативный KalkanCrypt. ✅\n'
          'Подлинность подписи ещё не проверена отдельно. '
          'Это НЕ транспортная WS-Security подпись Smart Bridge.\n'
          'Ничего не отправлено в ИСНА.';
    });
  }

  Future<void> _save() async {
    final value = signedXml;
    if (value == null || busy) return;
    setState(() => busy = true);
    try {
      final path = await FileSaver.instance.saveAs(
        name: 'nika-isna-local-xml-signature-test',
        bytes: Uint8List.fromList(utf8.encode(value)),
        fileExtension: 'xml',
        mimeType: MimeType.custom,
        customMimeType: 'application/xml',
      );
      if (mounted && path != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Пробный подписанный XML сохранён')),
        );
      }
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Не удалось сохранить XML: ' + error.toString());
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              color: theme.colorScheme.primary.withOpacity(.09),
              border: Border.all(color: theme.colorScheme.primary.withOpacity(.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('ИСНА · тестовая диагностика',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18)),
                const SizedBox(height: 8),
                const Text('Нативная проверка Smart Bridge и подписи через '
                    'KalkanCrypt. Никакого WebView, NCALayer или загрузки ЭЦП на сервер.'),
                const SizedBox(height: 10),
                const Text('Пока подписывается только демонстрационный XML, '
                    'без ИИН, БИН и налоговых данных. Подписанный XML остаётся '
                    'на телефоне, пока вы сами его не сохраните.',
                    style: TextStyle(fontSize: 12)),
              ],
            ),
          ),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: busy ? null : _check,
            icon: const Icon(Icons.network_check),
            label: const Text('Проверить доступность Smart Bridge'),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: busy ? null : _sign,
            icon: const Icon(Icons.key_rounded),
            label: const Text('Подписать пробный XML (.p12)'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: busy || signedXml == null ? null : _save,
            icon: const Icon(Icons.save_alt_rounded),
            label: const Text('Сохранить подписанный XML'),
          ),
          const SizedBox(height: 8),
          const OutlinedButton.icon(
            onPressed: null,
            icon: Icon(Icons.send_outlined),
            label: Text('Отправить в ИСНА (пока недоступно)'),
          ),
          if (busy) const LinearProgressIndicator(),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: theme.dividerColor),
            ),
            child: SelectableText(status, style: const TextStyle(fontSize: 13, height: 1.45)),
          ),
          const SizedBox(height: 12),
          const Text('Для настоящей отправки ещё требуются официальная XSD '
              'сервиса ИСНА, подтверждённые идентификаторы отправителя и '
              'подпись SOAP по WS-Security ГОСТ.',
              style: TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _NativeIsnaSignDialog extends StatefulWidget {
  final String xml;
  const _NativeIsnaSignDialog({required this.xml});

  @override
  State<_NativeIsnaSignDialog> createState() => _NativeIsnaSignDialogState();
}

class _NativeIsnaSignDialogState extends State<_NativeIsnaSignDialog> {
  final password = TextEditingController();
  bool signing = false;
  String? error;

  Future<void> _sign() async {
    if (signing) return;
    if (password.text.isEmpty) {
      setState(() => error = 'Введите пароль от файла ЭЦП .p12.');
      return;
    }
    setState(() {
      signing = true;
      error = null;
    });
    try {
      final signed = await MobileP12Signer.signEsfXml(
        payload: widget.xml,
        password: password.text,
        saveKey: false,
      );
      if (mounted) Navigator.of(context).pop(signed);
    } catch (exception) {
      if (mounted) setState(() => error = exception.toString());
    } finally {
      if (mounted) setState(() => signing = false);
    }
  }

  @override
  void dispose() {
    password.clear();
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Тест подписи ИСНА · .p12'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Выберите именно ЭЦП ТОО, сертификат которой '
                  'использован в заявке Smart Bridge. '
                  'Ключ и пароль не передаются в Nika Business. '
                  'Файл ключа для этого теста не сохраняется.'),
              const SizedBox(height: 14),
              TextField(
                controller: password,
                obscureText: true,
                enabled: !signing,
                decoration: const InputDecoration(labelText: 'Пароль ЭЦП'),
              ),
              if (error != null) ...[
                const SizedBox(height: 10),
                Text(error!, style: const TextStyle(color: Colors.red)),
              ],
              if (signing) const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator(),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: signing ? null : () => Navigator.pop(context),
            child: const Text('Отмена'),
          ),
          FilledButton.icon(
            onPressed: signing ? null : _sign,
            icon: const Icon(Icons.key_rounded),
            label: const Text('Выбрать .p12 и подписать'),
          ),
        ],
      );
}
