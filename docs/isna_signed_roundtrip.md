# ISNA TEST: Android -> VPS signed SOAP round trip

This diagnostic is **offline with respect to the government gateway**. No
FNO_INTEGRATION / SOAP POST to Smart Bridge is made by this feature.

## Existing pieces (unchanged)
- GET `/accounting/isna/test/soap-draft` returns a **synthetic** SOAP with a
  deliberately invalid service ID and sender. It contains no taxpayer data.
- Android uses KalkanCrypt to sign `soap:Body` using WS-Security GOST and
  cryptographically verifies the signed document after serialization.

## New TEST-only verification
1. In Android, open **ИСНА · тестирование** and select
   **Получить SOAP с TEST-сервера и подписать локально**.
2. Choose the .p12 with the registered transport certificate and sign it.
   The private key and password stay on Android.
3. Tap **Проверить подписанный SOAP на TEST VPS**. The app sends *only*
   the signed synthetic diagnostic XML, including its public X.509 cert,
   to the authenticated Nika TEST route
   `POST /accounting/isna/test/verify-signed-soap`.
4. The server enforces TEST mode, session and active company; checks
   exact synthetic service ID/sender, SOAP/wsse XML structure, GOST
   algorithm URIs, Body reference, and fixed innocuous demo purpose.
   It performs **no** network request to BIP, does not persist the
   signed payload. When a GOST-enabled xmlsec1 verifier is available, it\n   also independently verifies the SOAP Body digest and XMLDSig signature.
5. Response includes `structureOk`, `sampleType`, `offlineOnly`,
   `cryptoVerifiedOnServer` (true only after successful server-side cryptographic\n   check), `cryptoVerificationStatus`, `soapSent=false`,
   `filingCreated=false`, an embedded-public-cert SHA256 fingerprint,
   and optional `registeredCertMatch`.

## Optional registered public certificate match

Install the public Smart Bridge `.cer` on the TEST VPS (outside a web root).
Set `ISNA_BIP_REGISTERED_CERT_PATH=/secure/isna/registered.cer` in the
TEST environment. This is a **public** certificate, never a .p12 or its
password. If absent, `registeredCertMatch=null` is reported; if configured
it compares DER bytes, **not** ownership or revocation. For a comparison that doesn't require copying the public certificate to VPS,\nset `ISNA_BIP_REGISTERED_CERT_SHA256=<64-character-hex-der-sha256>` in TEST.\nUse the fingerprint of the *same public DER certificate* independently\ncompared on Android. If both file and hash are configured, both must match.\nThis is a public certificate pin, not proof that the gateway registered it.

\n## Independent cryptographic verification on TEST VPS\n\n- The server extracts the public X.509 DER from the signed SOAP itself.\n  No private key, password, `.p12` or separate `.cer` upload is required\n  to verify the cryptographic signature.\n- Install an **xmlsec1 build with the Kazakhstan GOST 2015-512 signature and\n  Streebog digest transforms enabled**. A stock Ubuntu `apt install xmlsec1`\n  may not support these algorithms. Check with:\n  `xmlsec1 --list-transforms | grep -i gostr34102015-gostr34112015-512`.\n- Optionally set `ISNA_XMLSEC1_BIN=/absolute/path/to/xmlsec1` in TEST.\n- Verification runs offline with an unmodified signed XML in a private\n  temporary directory, using the embedded public certificate, and checks\n  both `SignedInfo` and the `soap:Body` digest reference. Temporary files are\n  deleted after the check. Raw XML and subprocess diagnostics are not returned.\n- JSON `cryptoVerificationStatus` is one of `verified`, `invalid`,\n  `unavailable`, `unsupported`, `error`. Only `verified` sets\n  `cryptoVerifiedOnServer=true`. The Android UI does NOT enable the next\n  synthetic POST until crypto verification succeeds.\n- **Mathematically valid signature is not authorization by ШЭП.** Certificate\n  chain trust, revocation and Smart Bridge registration are separate checks.\n  An unconfigured public cert pin leaves `registeredCertMatch=null`.\n\nThis change does not enable tax filing and does not send anything to ШЭП.\n\n## Offline tests

```bash
cd /var/www/nika-business-test
sudo -u www-data .venv/bin/python -m unittest discover \
  -s tests -p 'test_isna_signed_roundtrip.py' -v
sudo -u www-data .venv/bin/python -m unittest discover \
  -s tests -p 'test_isna_fno_integration.py' -v
```

The tests use a synthetic *non-cryptographic* signature to exercise structural
controls; they are deliberately not a substitute for the real Android
KalkanCrypt signing test.

**Production routes, live FNO submissions and the disabled ISNA Send button
remain unchanged.** A separate authorized workflow will be needed for
cryptographic verification of the actual taxpayer FNO and transmission.
