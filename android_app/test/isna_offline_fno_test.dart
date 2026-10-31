import 'package:flutter_test/flutter_test.dart';
import 'package:nika_business_app/screens/isna_test_panel.dart';

void main() {
  test('local certificate comparison needs valid matching SHA-256 fingerprints', () {
    const a = 'CC9955B21C8977FB40EE2AA446029D4A5ECEF873855B1D614D3C16C4E3D3BE30';
    const b = 'CC9955B21C8977FB40EE2AA446029D4A5ECEF873855B1D614D3C16C4E3D3BE31';
    expect(isIsnaSameCertificateSha256(a, a.toLowerCase()), isTrue);
    expect(isIsnaSameCertificateSha256(a, b), isFalse);
    expect(isIsnaSameCertificateSha256('', a), isFalse);
    expect(isIsnaSameCertificateSha256(a, 'not-a-certificate'), isFalse);
    expect(isIsnaSameCertificateSha256(a, a + '0'), isFalse);
  });

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
