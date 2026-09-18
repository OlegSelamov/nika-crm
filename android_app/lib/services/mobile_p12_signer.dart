import 'package:flutter/services.dart';

class MobileP12Signer {
  static const MethodChannel _channel =
      MethodChannel('com.nikabusiness.app/signing');

  static Future<Map<String, dynamic>> signAlatauJws({
    required String payload,
    required String password,
  }) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(
        'signAlatauJwsWithP12',
        {
          'payload': payload,
          'password': password,
        },
      );

      if (result is Map) {
        return Map<String, dynamic>.from(result);
      }
      throw const PlatformException(
        code: 'INVALID_SIGN_RESULT',
        message: 'Android вернул некорректный результат подписи',
      );
    } on PlatformException {
      rethrow;
    }
  }
}
