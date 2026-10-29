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
   signed payload, and does not perform independent GOST verification.
5. Response includes `structureOk`, `sampleType`, `offlineOnly`,
   `cryptoVerifiedOnServer=false`, `soapSent=false`,
   `filingCreated=false`, an embedded-public-cert SHA256 fingerprint,
   and optional `registeredCertMatch`.

## Optional registered public certificate match

Install the public Smart Bridge `.cer` on the TEST VPS (outside a web root).
Set `ISNA_BIP_REGISTERED_CERT_PATH=/secure/isna/registered.cer` in the
TEST environment. This is a **public** certificate, never a .p12 or its
password. If absent, `registeredCertMatch=null` is reported; if configured
it compares DER bytes, **not** ownership or revocation. The server does not
claim the signature is cryptographically verified.

## Offline tests

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
