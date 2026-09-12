import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/scanner_feedback_service.dart';
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
  final scannedCodes = <String>{};
  bool pressed = false;
  bool scanBusy = false;
  int scanSession = 0;
  DateTime? pressedAt;

  @override
  void dispose() {
    scannerController.dispose();
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
      await ScannerFeedbackService.play();
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

class QuickScannerBottomBar extends StatelessWidget {
  final Future<void> Function(String code) onScan;
  final bool enabled;

  const QuickScannerBottomBar({
    super.key,
    required this.onScan,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        minimum: const EdgeInsets.fromLTRB(10, 0, 10, 8),
        child: Container(
          height: 72,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: AppColors.border),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(.08),
                blurRadius: 22,
                offset: const Offset(0, 7),
              ),
            ],
          ),
          child: Row(
            children: [
              const Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Быстрый сканер',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Удерживайте кнопку',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              HoldScannerButton(
                enabled: enabled,
                size: 50,
                onScan: onScan,
              ),
            ],
          ),
        ),
      );
}
