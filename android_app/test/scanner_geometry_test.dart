import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:nika_business_app/services/scanner_geometry.dart';

void main() {
  const capture = BarcodeCapture(size: Size(720, 1280));

  test('only a very small DataMatrix triggers the marking gate', () {
    const tiny = Barcode(format: BarcodeFormat.dataMatrix, size: Size(35, 35));
    const normal = Barcode(format: BarcodeFormat.dataMatrix, size: Size(180, 180));
    expect(isTinyDataMatrix(tiny, capture), isTrue);
    expect(isTinyDataMatrix(normal, capture), isFalse);
  });

  test('QR and EAN cannot trigger marking zoom', () {
    const qr = Barcode(format: BarcodeFormat.qrCode, size: Size(25, 25));
    const ean = Barcode(format: BarcodeFormat.ean13, size: Size(30, 10));
    expect(isTinyDataMatrix(qr, capture), isFalse);
    expect(isTinyDataMatrix(ean, capture), isFalse);
  });

  test('missing camera dimensions do not trigger zoom', () {
    const tiny = Barcode(format: BarcodeFormat.dataMatrix, size: Size(20, 20));
    expect(isTinyDataMatrix(tiny, const BarcodeCapture()), isFalse);
  });
}
