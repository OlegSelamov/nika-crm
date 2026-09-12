import 'package:flutter/services.dart';

class ScannerFeedbackService {
  static const _channel = MethodChannel('com.nikabusiness.app/scanner');

  static Future<void> play() async {
    try {
      await _channel.invokeMethod<void>('playBeep');
    } catch (_) {
      await SystemSound.play(SystemSoundType.alert);
    }
    await HapticFeedback.heavyImpact();
  }
}
