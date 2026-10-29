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
      '<Nonce>$id</Nonce>'
      '<Submission>false</Submission>'
      '</NikaIsnaTest>';
}

// Inert payload used only to test signing SOAP Body in wsse:Security. Never
// contains a registered service ID, taxpayer information, or requestData.
String buildIsnaSoapDemoXml({String? nonce}) {
  final id = nonce ?? DateTime.now().toUtc().microsecondsSinceEpoch.toString();
  return '<?xml version="1.0" encoding="UTF-8"?>'
      '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
      'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
      '<soap:Header/>'
      '<soap:Body wsu:Id="id-$id">'
      '<test:NikaWsSecurityTest xmlns:test="urn:nikabusiness:offline-soap-test:1">'
      '<test:Submission>false</test:Submission>'
      '<test:Purpose>Offline WS-Security signing compatibility only</test:Purpose>'
      '</test:NikaWsSecurityTest>'
      '</soap:Body></soap:Envelope>';
}

// Official FNO_INTEGRATION SOAP *shape*, but an intentionally invalid form
// code 000.00 and a fake sender. Both signatures are created on Android.
// NEVER use this in the filing flow and NEVER forward it to Smart Bridge.
String buildIsnaOfflineFnoXml() =>
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<root><data><![CDATA['
    '{"code":"000.00","fnoDto":{"nikaOfflineDemo":true}}'
    ']]></data></root>';

String buildIsnaOfflineFnoSoap(String signedFnoXml, {String? nonce}) {
  if (signedFnoXml.length > 100000 ||
      !signedFnoXml.contains('Signature') ||
      signedFnoXml.contains('<!DOCTYPE') ||
      signedFnoXml.contains('<!ENTITY')) {
    throw StateError('Ожидалась только пробная подписанная ФНО.');
  }
  final id = nonce ?? DateTime.now().toUtc().microsecondsSinceEpoch.toString();
  final date = DateTime.now().toUtc().toIso8601String();
  final escaped = const HtmlEscape(HtmlEscapeMode.element).convert(signedFnoXml);
  return '<?xml version="1.0" encoding="UTF-8"?>'
      '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
      'xmlns:typ="http://bip.bee.kz/SyncChannel/v10/Types" '
      'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
      '<soap:Header/><soap:Body wsu:Id="id-fno-offline-$id">'
      '<typ:SendMessage><request><requestInfo>'
      '<messageId>00000000-0000-4000-8000-000000000001</messageId>'
      '<serviceId>FNO_INTEGRATION</serviceId>'
      '<messageDate>$date</messageDate>'
      '<sender><senderId>nika-fno-offline-only</senderId></sender>'
      '</requestInfo><requestData>'
      '<data xmlns:xs="http://www.w3.org/2001/XMLSchema" '
      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xsi:type="xs:string">$escaped</data>'
      '</requestData></request></typ:SendMessage>'
      '</soap:Body></soap:Envelope>';
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
  String? signedServerDemoSoap;
  bool signedServerSoapVerifiedByVps = false;
  String signedFileName = 'nika-isna-local-xml-signature-test';

  Future<void> _check() async {
    if (busy) return;
    setState(() {
      busy = true;
      status = 'Проверяем Smart Bridge (TEST/VPN). SOAP и ФНО не отправляются…';
    });
    try {
      final response = await ApiService.isnaTestDiagnostics();
      if (!mounted) return;
      final tcpOk = response['tcpOk'] == true;
      setState(() {
        status = [
          'Источник: ' + (response['networkCheckedFrom'] ?? 'TEST VPS').toString(),
          'TCP: ' + (tcpOk ? 'соединение установлено' : 'недоступно'),
          'HTTP: ' + (response['httpStatus']?.toString() ?? 'не проверен'),
          'Статус: ' + (response['tcpMessage'] ?? '').toString(),
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
      signedServerDemoSoap = null;
      signedServerSoapVerifiedByVps = false;
      signedFileName = 'nika-isna-local-xml-signature-test';
      status = 'Пробный XML подписан через нативный KalkanCrypt. ✅\n'
          'Подлинность подписи ещё не проверена отдельно. '
          'Это НЕ транспортная WS-Security подпись Smart Bridge.\n'
          'Ничего не отправлено в ИСНА.';
    });
  }

  Future<void> _signSoap() async {
    if (busy) return;
    final soap = buildIsnaSoapDemoXml();
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _NativeIsnaSignDialog(xml: soap, soapMode: true),
    );
    if (result == null || !mounted) return;
    final value = (result['signedXml'] ?? '').toString();
    if (result['signatureVerified'] != true ||
        !value.contains('<wsse:Security')) {
      setState(() => status = 'Не удалось подтвердить локальную подпись SOAP.');
      return;
    }
    setState(() {
      signedXml = value;
      signedServerDemoSoap = null;
      signedServerSoapVerifiedByVps = false;
      signedFileName = 'nika-isna-wssecurity-offline-test';
      status = 'Тестовый SOAP подписан в wsse:Security через KalkanCrypt. ✅\n'
          'Подпись SOAP Body проверена криптомодулем локально. ✅\n'
          'Нет serviceId ФНО, налоговых данных и отправки в Smart Bridge.\n'
          'Валидация подписи сервером ШЭП ещё не проводилась.';
    });
  }

  Future<void> _signServerSoap() async {
    if (busy) return;
    setState(() {
      signedServerDemoSoap = null;
      signedServerSoapVerifiedByVps = false;
      busy = true;
      status = 'Получаем безопасный SOAP от TEST-сервера Nika Business…';
    });
    try {
      final response = await ApiService.isnaTestUnsignedServerSoap();
      if (!mounted) return;
      final xml = (response['soapXml'] ?? '').toString();
      if (response['offlineOnly'] != true ||
          response['soapSent'] != false ||
          response['hasTaxpayerData'] != false ||
          response['hasGatewayPassword'] != false ||
          !xml.contains('NIKA_ISNA_OFFLINE_SIGNING_ONLY')) {
        throw StateError('TEST-сервер не вернул подтверждённую офлайн-заглушку.');
      }
      setState(() => busy = false);
      final result = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _NativeIsnaSignDialog(xml: xml, soapMode: true),
      );
      if (result == null || !mounted) {
        if (mounted) setState(() => status = 'Подпись отменена. Ничего не отправлено.');
        return;
      }
      final signed = (result['signedXml'] ?? '').toString();
      if (result['signatureVerified'] != true ||
          !signed.contains('<wsse:Security')) {
        throw StateError('KalkanCrypt не подтвердил подпись SOAP.');
      }
      setState(() {
        signedXml = signed;
        signedServerDemoSoap = signed;
        signedServerSoapVerifiedByVps = false;
        signedFileName = 'nika-isna-server-soap-offline-test';
        status = 'SOAP получен с TEST-сервера. ✅\n'
            'SOAP Body подписан на Android через KalkanCrypt. ✅\n'
            'Подпись проверена локально после сериализации. ✅\n'
            'Это синтетический serviceId без налоговых данных и пароля.\n'
            'В ШЭП ничего не отправлялось.';
      });
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Ошибка теста сервер → Android: $error\n'
            'SOAP и ФНО не отправлялись в ШЭП.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _verifySignedServerSoap() async {
    final soap = signedServerDemoSoap;
    if (busy || soap == null) return;
    setState(() {
      busy = true;
      status = 'Проверяем подписанную офлайн-заглушку на Nika TEST VPS…';
    });
    try {
      // Only a locally Kalkan-verified SYNTHETIC SOAP produced by the
      // server -> Android signing test may reach this endpoint.
      final result = await ApiService.isnaTestVerifySignedSoap(soap);
      if (!mounted) return;
      if (result['structureOk'] != true ||
          result['offlineOnly'] != true ||
          result['soapSent'] != false ||
          result['filingCreated'] != false ||
          result['cryptoVerifiedOnServer'] != false ||
          result['sampleType'] != 'test-server-bip-demo') {
        throw StateError('TEST-сервер вернул неожиданный результат.');
      }
      final certMatch = result['registeredCertMatch'];
      final certStatus = certMatch == true
          ? 'Совпадает с зарегистрированным публичным .cer. ✅'
          : certMatch == false
              ? 'НЕ совпадает с настроенным .cer на сервере. ❌'
              : 'Сравнение с .cer на VPS ещё не настроено.';
      setState(() {
        signedServerSoapVerifiedByVps = true;
        status = 'Android → Nika TEST VPS: подписанный SOAP принят. ✅\n'
            'Синтетический SOAP прошёл проверку структуры. ✅\n'
            '$certStatus\n'
            'Криптографически подпись проверена только на Android.\n'
            'На VPS подпись криптографически НЕ проверялась.\n'
            'В ШЭП и ИСНА ничего не отправлено, декларация не создавалась.';
      });
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Не удалось проверить SOAP на TEST VPS: $error\n'
            'В ШЭП и ИСНА ничего не отправлялось.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _sendSignedServerSoapToShep() async {
    final soap = signedServerDemoSoap;
    if (busy || soap == null || !signedServerSoapVerifiedByVps) return;
    // The gateway really receives an HTTP POST; require a separate,
    // non-dismissible user consent before the single request.
    final approved = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('Отправить пробный SOAP в тестовый ШЭП?'),
        content: const Text(
          'Это НАСТОЯЩИЙ сетевой запрос через TEST VPS и IPsec в тестовый '
          'ШЭП. Отправится только подписанная демонстрационная заглушка '
          'без ИИН, БИН и налоговых данных с заведомо несуществующим '
          'serviceId. Шлюз, скорее всего, ответит ошибкой. '
          'Настоящая декларация НЕ подаётся.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Отправить тестовый SOAP'),
          ),
        ],
      ),
    );
    if (approved != true || !mounted) return;
    setState(() {
      busy = true;
      signedServerSoapVerifiedByVps = false; // one explicit user action
      status = 'Отправляем подписанный синтетический SOAP через TEST VPS → IPsec → ШЭП…';
    });
    try {
      final result = await ApiService.isnaTestSendSyntheticToShep(soap);
      if (!mounted) return;
      final contacted = result['gatewayContacted'] == true;
      final statusCode = result['httpStatus']?.toString() ?? 'нет';
      final fault = result['soapFault'] == true;
      final faultMessage = (result['faultMessage'] ?? '').toString();
      setState(() {
        status = contacted
            ? 'Настоящий TEST HTTP POST выполнен. ✅\n'
                'Ответ тестового ШЭП: HTTP $statusCode\n'
                'SOAP Fault: ${fault ? "да" : "нет/не определён"}\n'
                '${faultMessage.isEmpty ? "" : "Описание шлюза: $faultMessage\n"}'
                'Это не подтверждает регистрацию системы или принятие подписи.\n'
                'Настоящая декларация НЕ отправлялась.'
            : 'Тестовый ШЭП не подтвердил приём HTTP POST.\n'
                'Налоговые данные не отправлялись.';
      });
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Ошибка TEST SOAP POST: $error\n'
            'Ни одна настоящая ФНО не подавалась.');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _signFnoOfflineDouble() async {
    if (busy) return;
    setState(() {
      signedServerDemoSoap = null;
      signedServerSoapVerifiedByVps = false;
      status = 'Формируем пробную ФНО 000.00 без персональных данных…';
    });
    try {
      final inner = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _NativeIsnaSignDialog(xml: buildIsnaOfflineFnoXml()),
      );
      if (inner == null || !mounted) {
        if (mounted) setState(() => status = 'Тест отменён. Ничего не отправлено.');
        return;
      }
      final signedInner = (inner['signedXml'] ?? '').toString();
      final unsignedSoap = buildIsnaOfflineFnoSoap(signedInner);
      final outer = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _NativeIsnaSignDialog(xml: unsignedSoap, soapMode: true),
      );
      if (outer == null || !mounted) {
        if (mounted) setState(() => status = 'Вторая подпись отменена. Ничего не отправлено.');
        return;
      }
      if (outer['signatureVerified'] != true ||
          outer['innerSignatureVerified'] != true) {
        throw StateError('Не подтверждены обе подписи KalkanCrypt.');
      }
      setState(() {
        signedXml = (outer['signedXml'] ?? '').toString();
        signedFileName = 'nika-isna-fno-double-signed-OFFLINE-ONLY';
        status = 'Пробная ФНО 000.00 подписана XMLDSig. ✅\n'
            'Внутренняя подпись проверена KalkanCrypt. ✅\n'
            'Внешний SOAP FNO_INTEGRATION подписан WS-Security. ✅\n'
            'Подпись SOAP Body проверена KalkanCrypt. ✅\n'
            'senderId вымышленный, форма заведомо недействительна.\n'
            'Это ТОЛЬКО локальный тест: на VPS и в ШЭП ничего не отправлено.';
      });
    } catch (error) {
      if (mounted) {
        setState(() => status = 'Ошибка локальной проверки двух подписей: $error\n'
            'Ничего не отправлено в ШЭП или ИСНА.');
      }
    }
  }

  Future<void> _save() async {
    final value = signedXml;
    if (value == null || busy) return;
    setState(() => busy = true);
    try {
      final path = await FileSaver.instance.saveAs(
        name: signedFileName,
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
                    'без ИИН, БИН и налоговых данных. Только по отдельной кнопке '
                    'синтетический подписанный SOAP передаётся на TEST VPS для проверки.',
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
            onPressed: busy ? null : _signSoap,
            icon: const Icon(Icons.verified_user_outlined),
            label: const Text('Подписать SOAP WS-Security (.p12) — локально'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: busy ? null : _signServerSoap,
            icon: const Icon(Icons.cloud_download_outlined),
            label: const Text('Получить SOAP с TEST-сервера и подписать локально'),
          ),
          const SizedBox(height: 8),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: busy || signedServerDemoSoap == null
                ? null : _verifySignedServerSoap,
            icon: const Icon(Icons.fact_check_outlined),
            label: const Text('Проверить подписанный SOAP на TEST VPS'),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: busy || !signedServerSoapVerifiedByVps
                ? null : _sendSignedServerSoapToShep,
            icon: const Icon(Icons.send_rounded),
            label: const Text('Отправить пробный SOAP в TEST ШЭП'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: busy ? null : _signFnoOfflineDouble,
            icon: const Icon(Icons.layers_outlined),
            label: const Text('Проверить две подписи ФНО · локально'),
          ),
          OutlinedButton.icon(
            onPressed: busy || signedXml == null ? null : _save,
            icon: const Icon(Icons.save_alt_rounded),
            label: const Text('Сохранить подписанный XML'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
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
          const Text('TEST-диагностика не выполняет отправку ФНО. '
              'Реальная отправка требует проверки подписей и формата ФНО, '
              'а также отдельного включения разрешённого SOAP POST.',
              style: TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _NativeIsnaSignDialog extends StatefulWidget {
  final String xml;
  final bool soapMode;
  const _NativeIsnaSignDialog({required this.xml, this.soapMode = false});

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
      final signed = widget.soapMode
          ? await MobileP12Signer.signIsnaSoapDemo(
              payload: widget.xml,
              password: password.text,
            )
          : await MobileP12Signer.signEsfXml(
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
        title: Text(widget.soapMode ? 'Подпись SOAP WS-Security · .p12' : 'Тест подписи ИСНА · .p12'),
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
