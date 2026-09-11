import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../theme/app_theme.dart';

class HoldScannerButton extends StatefulWidget {
  final Future<void> Function(String code) onScan;
  final bool enabled;
  final double size;
  final String tooltip;

  const HoldScannerButton({
    super.key,
    required this.onScan,
    this.enabled = true,
    this.size = 48,
    this.tooltip = 'Удерживайте для сканирования',
  });

  @override
  State<HoldScannerButton> createState() => _HoldScannerButtonState();
}

class _HoldScannerButtonState extends State<HoldScannerButton> {
  final scannerController = MobileScannerController(
    autoStart: false,
    detectionSpeed: DetectionSpeed.normal,
  );
  final player = AudioPlayer();
  final beep = _createBarcodeBeep();
  final scannedCodes = <String>{};
  bool pressed = false;
  bool scanBusy = false;
  int scanSession = 0;
  DateTime? pressedAt;

  @override
  void initState() {
    super.initState();
    player.setPlayerMode(PlayerMode.lowLatency);
  }

  @override
  void dispose() {
    scannerController.dispose();
    player.dispose();
    super.dispose();
  }

  void _start() {
    if (!widget.enabled || pressed) return;
    pressedAt = DateTime.now();
    scannedCodes.clear();
    setState(() => pressed = true);
    final session = ++scanSession;
    _activateScanner(session);
  }

  Future<void> _activateScanner(int session) async {
    try {
      await scannerController.start();
      if (!pressed || session != scanSession) {
        await scannerController.stop();
      }
    } catch (_) {
      if (!mounted || session != scanSession) return;
      setState(() => pressed = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось запустить камеру')),
      );
    }
  }

  Future<void> _finish() async {
    if (!pressed) return;
    final wasQuickTap = pressedAt != null &&
        DateTime.now().difference(pressedAt!).inMilliseconds < 180;
    pressedAt = null;
    scanSession++;
    if (mounted) setState(() => pressed = false);
    await scannerController.stop();
    if (wasQuickTap && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.tooltip)),
      );
    }
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (!pressed || scanBusy || capture.barcodes.isEmpty) return;
    final code = capture.barcodes.first.rawValue?.trim() ?? '';
    if (code.isEmpty || scannedCodes.contains(code)) return;
    scannedCodes.add(code);
    scanBusy = true;
    try {
      try {
        await player.stop();
        await player.play(BytesSource(beep), volume: 1);
      } catch (_) {
        await SystemSound.play(SystemSoundType.alert);
      }
      await HapticFeedback.mediumImpact();
      await widget.onScan(code);
    } finally {
      scanBusy = false;
    }
  }

  @override
  Widget build(BuildContext context) => Tooltip(
        message: widget.tooltip,
        child: SizedBox(
          width: widget.size + 16,
          height: widget.size + 16,
          child: Stack(
            alignment: Alignment.center,
            clipBehavior: Clip.none,
            children: [
              Positioned.fill(
                child: IgnorePointer(
                  child: Opacity(
                    opacity: .01,
                    child: MobileScanner(
                      controller: scannerController,
                      onDetect: _onDetect,
                    ),
                  ),
                ),
              ),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapDown: widget.enabled ? (_) => _start() : null,
                onTapUp: widget.enabled ? (_) => _finish() : null,
                onTapCancel: widget.enabled ? _finish : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 120),
                  width: widget.size,
                  height: widget.size,
                  decoration: BoxDecoration(
                    color: !widget.enabled
                        ? AppColors.border
                        : pressed
                            ? const Color(0xFF1677FF)
                            : AppColors.primarySoft,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: pressed
                          ? const Color(0xFFD8F0FF)
                          : AppColors.primary.withOpacity(.22),
                      width: pressed ? 3 : 1,
                    ),
                    boxShadow: pressed
                        ? [
                            BoxShadow(
                              color: const Color(0xFF52B9FF).withOpacity(.82),
                              blurRadius: 26,
                              spreadRadius: 6,
                            ),
                            BoxShadow(
                              color: const Color(0xFF1677FF).withOpacity(.34),
                              blurRadius: 38,
                              spreadRadius: 9,
                            ),
                          ]
                        : const [],
                  ),
                  child: Icon(
                    Icons.qr_code_scanner_rounded,
                    color: pressed ? Colors.white : AppColors.primary,
                    size: widget.size * .5,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
}

Uint8List _createBarcodeBeep() {
  const sampleRate = 22050;
  const durationMs = 150;
  final sampleCount = sampleRate * durationMs ~/ 1000;
  final dataLength = sampleCount * 2;
  final bytes = Uint8List(44 + dataLength);
  final data = ByteData.view(bytes.buffer);

  void writeAscii(int offset, String value) {
    for (var i = 0; i < value.length; i++) {
      bytes[offset + i] = value.codeUnitAt(i);
    }
  }

  writeAscii(0, 'RIFF');
  data.setUint32(4, 36 + dataLength, Endian.little);
  writeAscii(8, 'WAVE');
  writeAscii(12, 'fmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, 1, Endian.little);
  data.setUint32(24, sampleRate, Endian.little);
  data.setUint32(28, sampleRate * 2, Endian.little);
  data.setUint16(32, 2, Endian.little);
  data.setUint16(34, 16, Endian.little);
  writeAscii(36, 'data');
  data.setUint32(40, dataLength, Endian.little);

  for (var i = 0; i < sampleCount; i++) {
    final progress = i / sampleCount;
    final frequency = 950 + (progress * 350);
    final attack = math.min(1.0, i / (sampleRate * .008));
    final fade = math.min(1.0, (sampleCount - i) / (sampleRate * .025));
    final sample = (math.sin(2 * math.pi * frequency * i / sampleRate) *
            28000 *
            attack *
            fade)
        .round();
    data.setInt16(44 + (i * 2), sample, Endian.little);
  }
  return bytes;
}
