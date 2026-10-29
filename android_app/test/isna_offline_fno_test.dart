import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/screens/isna_test_panel.dart';

void main() {
  test('transport certificate validity boundaries are enforced before WShEP POST', () {
    expect(
      isIsnaCertificateCurrent(
        notBeforeMs: 1000, notAfterMs: 3000, nowMs: 2000,
      ),
      isTrue,
    );
    expect(
      isIsnaCertificateCurrent(
        notBeforeMs: 1000, notAfterMs: 3000, nowMs: 3000,
      ),
      isFalse,
    );
    expect(
      isIsnaCertificateCurrent(
        notBeforeMs: 1000, notAfterMs: 3000, nowMs: 999,
      ),
      isFalse,
    );
    expect(
      isIsnaCertificateCurrent(
        notBeforeMs: null, notAfterMs: 3000, nowMs: 2000,
      ),
      isFalse,
    );
  });

  test('synthetic FNO uses deliberately invalid code and contains no identities', () {
    final inner = buildIsnaOfflineFnoXml();
    expect(inner, contains('<root><data><![CDATA['));
    expect(inner, contains('"code":"000.00"'));
    expect(inner, contains('"nikaOfflineDemo":true'));
    expect(inner, isNot(contains('taxpayerCode')));
    expect(inner, isNot(contains('creatorCode')));
  });

  test('official wire shape keeps the inner signed XML as xs:string text', () {
    const signed = '<root><data>x</data><Signature>offline</Signature></root>';
    final soap = buildIsnaOfflineFnoSoap(signed, nonce: '12345');
    expect(soap, contains('<serviceId>FNO_INTEGRATION</serviceId>'));
    expect(soap, contains('<senderId>nika-fno-offline-only</senderId>'));
    expect(soap, isNot(contains('<password>')));
    expect(soap, contains('xsi:type="xs:string"'));
    expect(soap, contains('&lt;root&gt;'));
    expect(soap, isNot(contains('<root><data>x</data>')));
    expect(soap, contains('wsu:Id="id-fno-offline-12345"'));
  });

  test('rejects missing signature and unsafe XML', () {
    expect(() => buildIsnaOfflineFnoSoap('<root/>'), throwsStateError);
    expect(
      () => buildIsnaOfflineFnoSoap('<!DOCTYPE root><root><Signature/></root>'),
      throwsStateError,
    );
    expect(
      () => buildIsnaOfflineFnoSoap('<root><Signature/></root>' + ('x' * 100001)),
      throwsStateError,
    );
  });
}
