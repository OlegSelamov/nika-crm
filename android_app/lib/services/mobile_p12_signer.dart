import 'package:flutter/services.dart';

class MobileP12Signer {
  static const MethodChannel _channel =
      MethodChannel('com.nikabusiness.app/signing');

  static Future<Map<String, dynamic>> capabilities() async {\n    final result = await _channel.invokeMethod<dynamic>('getSigningCapabilities');\n    if (result is Map) {\n      return Map<String, dynamic>.from(result);\n    }\n    throw PlatformException(\n      code: 'INVALID_CAPABILITIES',\n      message: 'Android не вернул состояние криптомодуля',\n    );\n  }\n  static Future<Map<String, dynamic>> signAlatauJws({
    required String payload,
    required String password,
  }) =>
      _invoke(
        'signAlatauJwsWithP12',
        payload: payload,
        password: password,
      );

  static Future<Map<String, dynamic>> signEsfRaw({
    required String payload,
    required String password,
  }) =>
      _invoke(
        'signEsfRawWithP12',
        payload: payload,
        password: password,
      );

  static Future<Map<String, dynamic>> signEsfXml({
    required String payload,
    required String password,
  }) =>
      _invoke(
        'signEsfXmlWithP12',
        payload: payload,
        password: password,
      );

  static Future<Map<String, dynamic>> _invoke(
    String method, {
    required String payload,
    required String password,
  }) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(
        method,
        {
          'payload': payload,
          'password': password,
        },
      );

      if (result is Map) {
        return Map<String, dynamic>.from(result);
      }

      // PlatformException is not a const class.
      throw PlatformException(
        code: 'INVALID_SIGN_RESULT',
        message: 'Android вернул некорректный результат подписи',
      );
    } on PlatformException {
      rethrow;
    }
  }
}
