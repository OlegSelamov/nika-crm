import 'dart:math' as math;

import 'package:mobile_scanner/mobile_scanner.dart';

// Camera-frame based gate: only a VERY SMALL DataMatrix is eligible.
// All linear codes, QR codes and normal-sized DataMatrix stay unzoomed.
bool isTinyDataMatrix(Barcode barcode, BarcodeCapture capture) {
  if (barcode.format != BarcodeFormat.dataMatrix) return false;
  final frame = capture.size;
  final bounds = barcode.size;
  if (frame.width <= 0 || frame.height <= 0 ||
      bounds.width <= 0 || bounds.height <= 0) {
    return false;
  }
  final shortestFrameSide = math.min(frame.width, frame.height);
  final longestCodeSide = math.max(bounds.width, bounds.height);
  return longestCodeSide / shortestFrameSide < 0.10;
}
