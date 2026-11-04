import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/services/isna_real_fno_payload.dart';

void main() {
  test('an official complete 910.00 request becomes unsigned inner XML', () {
    const source = '{"code":"910.00","fnoDto":{"entity":"TOO Nika & Travel",'
        '"quarter":2,"demo":false}}';
    final unsigned = buildUnsignedRealFnoXml(
      sourceJson: source, expectedCode: '910.00',
    );
    expect(unsigned, startsWith('<?xml version="1.0" encoding="UTF-8"?>'));
    expect(unsigned, contains('<root><data>'));
    expect(unsigned, contains('910.00'));
    expect(unsigned, contains('Nika &amp; Travel'));
    expect(unsigned, isNot(contains('<ds:Signature')));
    expect(unsigned, isNot(contains('FNO_INTEGRATION')));
    expect(unsigned, endsWith('</data></root>'));
  });

  test('never guesses fnoDto from an ISNA Values object', () {
    expect(
      () => buildUnsignedRealFnoXml(
        sourceJson: '{"bin":"123456789012","taxPeriod":2026}',
        expectedCode: '910.00',
      ),
      throwsFormatException,
    );
    expect(
      () => buildUnsignedRealFnoXml(
        sourceJson: '{"code":"910.00","fnoDto":{}}',
        expectedCode: '910.00',
      ),
      throwsFormatException,
    );
  });

  test('rejects mismatched form, fake data and extra wrapper fields', () {
    final inputs = [
      '{"code":"200.00","fnoDto":{"item":"x"}}',
      '{"code":"000.00","fnoDto":{"item":"x"}}',
      '{"code":"910.00","fnoDto":{"nikaOfflineDemo":true}}',
      '{"code":"910.00","fnoDto":{"item":"x"},"signature":true}',
    ];
    for (final source in inputs) {
      expect(
        () => buildUnsignedRealFnoXml(
          sourceJson: source, expectedCode: '910.00',
        ),
        throwsFormatException,
      );
    }
  });

  test('keeps numeric values and nested fields without fabricating defaults', () {
    final unsigned = buildUnsignedRealFnoXml(
      sourceJson: '{"code":"200.00","fnoDto":{"amount":0,'
          '"rows":[{"value":1.25},{"value":2.5}]}}',
      expectedCode: '200.00',
    );
    expect(unsigned, contains('"amount":0'));
    expect(unsigned, contains('"rows"'));
    expect(unsigned, contains('"value":1.25'));
    expect(unsigned, isNot(contains('signatureValue')));
  });

  test('rejects huge or malformed payloads', () {
    expect(
      () => buildUnsignedRealFnoXml(
        sourceJson: '{"code":"910.00","fnoDto":',
        expectedCode: '910.00',
      ),
      throwsFormatException,
    );
    expect(
      () => buildUnsignedRealFnoXml(
        sourceJson: 'x' * 100001,
        expectedCode: '910.00',
      ),
      throwsFormatException,
    );
  });
}
