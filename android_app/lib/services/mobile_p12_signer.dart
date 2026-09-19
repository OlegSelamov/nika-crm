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

  static Future<String?> loadSavedPassword() async {
    final result = await _channel.invokeMethod<dynamic>('loadSavedP12Password');
    if (result == null) return null;
    return result.toString();
  }

  static Future<void> savePassword(String password) async {
    await _channel.invokeMethod<void>(
      'saveP12Password',
      {'password': password},
    );
  }

  static Future<void> clearSavedPassword() async {
    await _channel.invokeMethod<void>('clearSavedP12Password');
  }

  static Future<Map<String, dynamic>> savedKeyInfo() async {
    final result = await _channel.invokeMethod<dynamic>('getSavedP12KeyInfo');
    if (result is Map) return Map<String, dynamic>.from(result);
    return <String, dynamic>{};
  }

  static Future<void> clearSavedKey() async {
    await _channel.invokeMethod<void>('clearSavedP12Key');
  }

  static Future<Map<String, dynamic>> signAlatauWithSavedKey({
    required String payload,
  }) async {
    final result = await _channel.invokeMethod<dynamic>(
      'signAlatauJwsWithSavedP12',
      {'payload': payload},
    );
    if (result is Map) return Map<String, dynamic>.from(result);
    throw PlatformException(
      code: 'INVALID_SIGN_RESULT',
      message: 'Android вернул некорректный результат подписи',
    );
  }

  static Future<Map<String, dynamic>> signAlatauJws({
    required String payload,
    required String password,
    bool saveKey = false,
  }) =>
      _invoke(
        'signAlatauJwsWithP12',
        payload: payload,
        password: password,
        saveKey: saveKey,
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
    bool saveKey = false,
  }) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(
        method,
        {
          'payload': payload,
          'password': password,
          'saveKey': saveKey,
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
