import 'package:flutter/services.dart';

class MobileP12Signer {
  static const MethodChannel _channel =
      MethodChannel('com.nikabusiness.app/signing');

  static Future<Map<String, dynamic>> capabilities() async {
    final result =
        await _channel.invokeMethod<dynamic>('getSigningCapabilities');
    if (result is Map) {
      return Map<String, dynamic>.from(result);
    }
    throw PlatformException(
      code: 'INVALID_CAPABILITIES',
      message: 'Android не вернул состояние криптомодуля',
    );
  }

  static Future<Map<String, dynamic>> signAlatauJws({
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

      throw PlatformException(
        code: 'INVALID_SIGN_RESULT',
        message: 'Android вернул некорректный результат подписи',
      );
    } on PlatformException {
      rethrow;
    }
  }
}
