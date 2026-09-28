import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/scanner_feedback_service.dart';

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
  bool scanned = false;
  bool _initialFocusApplied = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    scannerController = MobileScannerController(
      cameraResolution: const Size(1920, 1080),
      detectionSpeed: DetectionSpeed.noDuplicates,
      formats: _scannerFormats,
      autoZoom: true,
      initialZoom: 0.12,
    )..addListener(_applyInitialFocus);
  }

  Future<void> _applyInitialFocus() async {
    if (_initialFocusApplied || !scannerController.value.isRunning) return;

    _initialFocusApplied = true;
    try {
      await scannerController.setFocusPoint(const Offset(0.5, 0.5));
    } catch (_) {
      // Some cameras do not expose manual focus points.
      // Continuous autofocus still remains active.
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!scannerController.value.hasCameraPermission) return;

    switch (state) {
      case AppLifecycleState.resumed:
        _initialFocusApplied = false;
        unawaited(scannerController.start());
      case AppLifecycleState.inactive:
        unawaited(scannerController.stop());
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
        return;
    }
  }

  Future<void> onDetect(BarcodeCapture capture) async {
    if (scanned || capture.barcodes.isEmpty) return;

    final barcode = capture.barcodes.first.rawValue?.trim();

    if (barcode == null || barcode.isEmpty) return;

    scanned = true;

    await ScannerFeedbackService.play();
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    Navigator.pop(context, barcode);

    messenger.showSnackBar(
      SnackBar(
        content: Text('Считан штрихкод: $barcode'),
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    scannerController.removeListener(_applyInitialFocus);
    unawaited(scannerController.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Сканер'),
        backgroundColor: const Color(0xFF0B1F3A),
        foregroundColor: Colors.white,
      ),
      body: Stack(
        children: [
          MobileScanner(
            controller: scannerController,
            onDetect: onDetect,
            tapToFocus: true,
          ),
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
          const Positioned(
            bottom: 40,
            left: 20,
            right: 20,
            child: Text(
              'Наведите камеру на код. Для мелкого DataMatrix коснитесь кода для фокусировки.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
