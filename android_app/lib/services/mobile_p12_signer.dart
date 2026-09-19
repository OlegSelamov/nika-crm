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

  static Future<Map<String, dynamic>?> loadSavedEsfAuth() async {
    final result = await _channel.invokeMethod<dynamic>('loadSavedEsfAuth');
    if (result == null) return null;
    if (result is Map) return Map<String, dynamic>.from(result);
    return null;
  }

  static Future<void> saveEsfAuth({
    required String iin,
    required String password,
    required String profileType,
  }) async {
    await _channel.invokeMethod<void>(
      'saveEsfAuth',
      {
        'iin': iin,
        'password': password,
        'profile_type': profileType,
      },
    );
  }

  static Future<void> clearSavedEsfAuth() async {
    await _channel.invokeMethod<void>('clearSavedEsfAuth');
  }

  static Future<Map<String, dynamic>> signAlatauWithSavedKey({
    required String payload,
    int? signingTimestampMs,
  }) =>
      _invokeSaved(
        'signAlatauJwsWithSavedP12',
        payload,
        signingTimestampMs: signingTimestampMs,
      );

  static Future<Map<String, dynamic>> signEsfRawWithSavedKey({
    required String payload,
  }) =>
      _invokeSaved('signEsfRawWithSavedP12', payload);

  static Future<Map<String, dynamic>> signEsfXmlWithSavedKey({
    required String payload,
  }) =>
      _invokeSaved('signEsfXmlWithSavedP12', payload);

  static Future<Map<String, dynamic>> signAlatauJws({
    required String payload,
    required String password,
    bool saveKey = false,
    int? signingTimestampMs,
  }) =>
      _invoke(
        'signAlatauJwsWithP12',
        payload: payload,
        password: password,
        saveKey: saveKey,
        signingTimestampMs: signingTimestampMs,
      );

  static Future<Map<String, dynamic>> signEsfRaw({
    required String payload,
    required String password,
    bool saveKey = false,
  }) =>
      _invoke(
        'signEsfRawWithP12',
        payload: payload,
        password: password,
        saveKey: saveKey,
      );

  static Future<Map<String, dynamic>> signEsfXml({
    required String payload,
    required String password,
    bool saveKey = false,
  }) =>
      _invoke(
        'signEsfXmlWithP12',
        payload: payload,
        password: password,
        saveKey: saveKey,
      );

  static Future<Map<String, dynamic>> _invokeSaved(
    String method,
    String payload, {
    int? signingTimestampMs,
  }) async {
    final result = await _channel.invokeMethod<dynamic>(
      method,
      {
        'payload': payload,
        if (signingTimestampMs != null)
          'signingTimestampMs': signingTimestampMs,
      },
    );
    if (result is Map) return Map<String, dynamic>.from(result);
    throw PlatformException(
      code: 'INVALID_SIGN_RESULT',
      message: 'Android вернул некорректный результат подписи',
    );
  }

  static Future<Map<String, dynamic>> _invoke(
    String method, {
    required String payload,
    required String password,
    bool saveKey = false,
    int? signingTimestampMs,
  }) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(
        method,
        {
          'payload': payload,
          'password': password,
          'saveKey': saveKey,
          if (signingTimestampMs != null)
            'signingTimestampMs': signingTimestampMs,
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
