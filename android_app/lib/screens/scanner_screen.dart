import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/product_code_parser.dart';
import '../services/scanner_feedback_service.dart';
import '../services/scanner_geometry.dart';

const _scannerFormats = <BarcodeFormat>[
  BarcodeFormat.dataMatrix,
  BarcodeFormat.ean13,
  BarcodeFormat.ean8,
  BarcodeFormat.upcA,
  BarcodeFormat.upcE,
  BarcodeFormat.code128,
  BarcodeFormat.code39,
  BarcodeFormat.code93,
  BarcodeFormat.codabar,
  BarcodeFormat.itf,
  BarcodeFormat.qrCode,
];

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen>
    with WidgetsBindingObserver {
  late final MobileScannerController scannerController;
  late final MobileScannerController _tinyMatrixController;

  bool scanned = false;
  bool _markingMode = false;
  bool _changingMode = false;

  MobileScannerController get _activeController =>
      _markingMode ? _tinyMatrixController : scannerController;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    scannerController = MobileScannerController(
      cameraResolution: const Size(1920, 1080),
      detectionSpeed: DetectionSpeed.normal,
      detectionTimeoutMs: 90,
      formats: _scannerFormats,
      // Ordinary barcodes and large DataMatrix must not trigger zoom.
      autoZoom: false,
    );
    // A separate native scanner automatically zooms only when explicitly
    // scanning tiny marking. Regular EAN / large DataMatrix stay untouched.
    _tinyMatrixController = MobileScannerController(
      cameraResolution: const Size(1920, 1080),
      detectionSpeed: DetectionSpeed.normal,
      detectionTimeoutMs: 90,
      formats: const [BarcodeFormat.dataMatrix],
      autoZoom: true,
    );
  }

  // Enter marking mode only for a tiny *unreadable* DataMatrix candidate
  // with camera-reported geometry. No zoom-trigger heuristics for EAN/QR.
  void _checkTinyCandidate(BarcodeCapture capture) {
    if (_markingMode || scanned) return;
    for (final barcode in capture.barcodes) {
      if (barcode.rawValue?.trim().isNotEmpty ?? false) continue;
      if (isTinyDataMatrix(barcode, capture)) {
        unawaited(_setMarkingMode(true));
        return;
      }
    }
  }

  Future<void> _setMarkingMode(bool enabled) async {
    if (!mounted || scanned || _changingMode || _markingMode == enabled) return;
    _changingMode = true;
    try {
      // Never run both camera controllers simultaneously.
      await _activeController.stop();
      if (!mounted || scanned) return;
      setState(() => _markingMode = enabled);
      // The newly attached MobileScanner starts its own controller.
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось переключить камеру')),
        );
      }
    } finally {
      _changingMode = false;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_activeController.value.hasCameraPermission) return;

    switch (state) {
      case AppLifecycleState.resumed:
        if (!_changingMode) unawaited(_activeController.start());
      case AppLifecycleState.inactive:
        unawaited(_activeController.stop());
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
        return;
    }
  }

  Future<void> onDetect(BarcodeCapture capture) async {
    if (scanned || _changingMode || capture.barcodes.isEmpty) return;

    String? rawCode;
    for (final barcode in capture.barcodes) {
      final raw = barcode.rawValue;
      // Validate without trimming the actual GS1 payload: GS, serial and
      // crypto symbols must reach reKassa exactly as the scanner returned.
      if (raw != null && raw.trim().isNotEmpty) {
        rawCode = raw;
        break;
      }
    }

    if (rawCode == null) {
      _checkTinyCandidate(capture);
      return;
    }

    final parsed = ScannedProductCode.parse(rawCode);
    if (parsed.isEmpty) return;
    scanned = true;
    await ScannerFeedbackService.play();
    if (!mounted) return;

    // Lookup and all visible UI use parsed.lookupCode in the caller.
    // The complete marking is returned silently, never shown as raw text.
    Navigator.pop(context, rawCode);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(scannerController.dispose());
    unawaited(_tinyMatrixController.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(_markingMode ? 'Сканер · маркировка' : 'Сканер'),
        backgroundColor: const Color(0xFF0B1F3A),
        foregroundColor: Colors.white,
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final size = constraints.biggest;
          // ML Kit decodes DataMatrix only if it intersects the exact
          // center of the camera input. The reticle must follow that center.
          final targetY = size.height * 0.5;

          const targetSize = 82.0;
          const loupeWidth = 238.0;
          const loupeHeight = 218.0;
          final loupeCenterY = targetY + 190;
          final loupeTop = loupeCenterY - loupeHeight / 2;

          return Stack(
            fit: StackFit.expand,
            children: [
              MobileScanner(
                key: ValueKey<bool>(_markingMode),
                controller: _activeController,
                // mobile_scanner 7.2.0 supports tapping dense codes to focus.
                tapToFocus: true,
                onDetect: onDetect,
              ),

              // For tiny symbols ML Kit cannot localize, allow explicit
              // marking mode rather than zooming ordinary codes on its own.
              Positioned(
                top: 12,
                right: 14,
                child: FilledButton.tonalIcon(
                  onPressed: _changingMode
                      ? null
                      : () => _setMarkingMode(!_markingMode),
                  icon: Icon(
                    _markingMode
                        ? Icons.zoom_out_map_rounded
                        : Icons.center_focus_strong_rounded,
                    size: 18,
                  ),
                  label: Text(
                    _markingMode ? 'Обычный сканер' : 'Мелкий DataMatrix',
                  ),
                ),
              ),

              if (_markingMode)
                Positioned(
                  left: (size.width - loupeWidth) / 2,
                  top: loupeTop,
                  child: IgnorePointer(
                    child: RawMagnifier(
                      size: const Size(loupeWidth, loupeHeight),
                      magnificationScale: 2.35,
                      focalPointOffset: Offset(0, targetY - loupeCenterY),
                      clipBehavior: Clip.antiAlias,
                      decoration: MagnifierDecoration(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                          side: const BorderSide(
                            color: Colors.white,
                            width: 2,
                          ),
                        ),
                        shadows: const [
                          BoxShadow(
                            blurRadius: 16,
                            spreadRadius: 1,
                            offset: Offset(0, 5),
                            color: Color(0x66000000),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

              if (_markingMode)
                Positioned(
                  left: (size.width - targetSize) / 2,
                  top: targetY - targetSize / 2,
                  child: IgnorePointer(
                    child: Container(
                      width: targetSize,
                      height: targetSize,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Colors.white,
                          width: 2.5,
                        ),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x55000000),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              else
                IgnorePointer(
                  child: Center(
                    child: Container(
                      width: 260,
                      height: 180,
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: Colors.white,
                          width: 3,
                        ),
                        borderRadius: BorderRadius.circular(18),
                      ),
                    ),
                  ),
                ),

              if (_markingMode)
                Positioned(
                  top: 70,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: IgnorePointer(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 7,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xB3000000),
                          borderRadius: BorderRadius.circular(18),
                        ),
                        child: const Text(
                          'Режим маркировки',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),

              Positioned(
                bottom: 40,
                left: 20,
                right: 20,
                child: IgnorePointer(
                  child: Text(
                    _markingMode
                        ? 'DataMatrix в центре · коснитесь квадрата для фокуса'
                        : 'Штрихкод и крупный DataMatrix: без увеличения',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      shadows: [
                        Shadow(
                          blurRadius: 5,
                          color: Colors.black,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
