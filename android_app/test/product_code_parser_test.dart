import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/product_code_parser.dart';

void main() {
  group('ScannedProductCode', () {
    test('keeps a regular EAN-13 unchanged', () {
      final code = ScannedProductCode.parse('4870001234567');

      expect(code.lookupCode, '4870001234567');
      expect(code.lookupCandidates, ['4870001234567']);
      expect(code.isMarkingCode, isFalse);
    });

    test('extracts EAN-13 and GTIN-14 from a compact GS1 code', () {
      final code = ScannedProductCode.parse(
        '010487000123456721SERIAL\u001d91CRYPTO',
      );

      expect(code.gtin, '04870001234567');
      expect(code.ean13, '4870001234567');
      expect(code.lookupCode, '4870001234567');
      expect(code.lookupCandidates, [
        '4870001234567',
        '04870001234567',
      ]);
      expect(code.markingCode, '010487000123456721SERIAL\u001d91CRYPTO');
    });

    test('removes a scanner AIM prefix but preserves the marking payload', () {
      final code = ScannedProductCode.parse(
        ']d2010487000123456721SERIAL',
      );

      expect(code.lookupCode, '4870001234567');
      expect(code.markingCode, '010487000123456721SERIAL');
    });

    test('supports the human-readable parenthesized GS1 form', () {
      final code = ScannedProductCode.parse(
        '(01)04870001234567(21)SERIAL',
      );

      expect(code.gtin, '04870001234567');
      expect(code.lookupCode, '4870001234567');
      expect(code.isMarkingCode, isTrue);
    });

    test('matches an item whose barcode is stored as EAN-13', () {
      final code = ScannedProductCode.parse(
        '010487000123456721SERIAL',
      );

      expect(code.matchesItem({'barcode': '4870001234567'}), isTrue);
      expect(code.matchesItem({'gtin': '04870001234567'}), isTrue);
      expect(code.matchesItem({'barcode': '1234567890123'}), isFalse);
    });
  });
}
