# Smart Bridge / ИСНА: TEST SOAP integration

## Verified on 2026-10-28 and confirmed co-hosting on 2026-10-29 (VPS 47167)

- IKEv2 and IPsec CHILD_SA: established for local `195.49.215.49/32` → remote `195.12.113.7/32`.
- TCP connection to `195.12.113.7:80`: succeeded.
- HTTP GET `http://195.12.113.7/bip-sync-wss-gost/`: 200 and a SyncChannel v10 SOAP WSDL.
- **No signed POST was performed; no tax form was submitted.**

## Code already present

- `services/isna_bip.py`: XML wrapper, offline diagnostics, external WS-Security signer hook, and transport POST helper.
- `routes/accounting.py`: creates internal JSON drafts for 910/200; its `ISNA_GATEWAY_URL` JSON workflow is **NOT** the Smart Bridge SOAP integration.
- Do not point `ISNA_GATEWAY_URL` directly at the SOAP URL: the JSON format is incompatible.
- The WSDL from the test endpoint advertises an unrelated internal SOAP address. Always use the URL explicitly provided in the approved Smart Bridge application.

## In-app TEST diagnostics and demonstration XML signing

- Open `https://test.nikabusiness.com/accounting/report?form_type=910` as an authenticated company user.
- The **TEST-only** ISNA diagnostics card checks a short TCP connection **from the TEST VPS** and locally signs a harmless dummy XML with browser NCALayer. It is NOT an official form, NOT a transport WS-Security signature, and has NO real SOAP submission action.
- The optional downloaded signed XML contains certificate/public key material; share it only as appropriate and never include the private `.p12` or its password.
- The diagnostic endpoint `GET /accounting/isna/test/diagnostics` requires login, active company and explicit `APP_MODE=test`. It never accepts a user-controlled URL or a SOAP payload.
- The Android TEST app is native Flutter. Its Accounting screen contains **ИСНА TEST · Проверка ЭЦП** (and an **ИСНА TEST** tab). The diagnostic screen uses the native Kotlin/KalkanCrypt `MobileP12Signer.signEsfXml` file picker, not WebView or NCALayer. It signs a non-sensitive sample locally without saving the selected key (`saveKey:false`). After updating the Android source, a **new isolated TEST APK** must be installed; a website deploy alone cannot update the native Flutter interface.
- The "Отправить в ИСНА" button in this new panel is **disabled** until we receive official ISNA service XSD, registered sender identity and working GOST WS-Security transport signer.
- **Confirmed on 2026-10-29:** `nika-business-test` runs on the very same VPS `47167` as StrongSwan IPsec. TEST diagnostics now bind the outgoing TCP/HTTP GET socket to `195.49.215.49`, without an SSH bridge. The VPN host is not separate. See [isna_vpn_probe_setup.md](isna_vpn_probe_setup.md) for an unprivileged service-account verification command.

## Confirm before a signed test

1. Exact approved Smart Bridge **`serviceId`** for ISNA (the code defaults `FNO_INTEGRATION`, but the default is **unverified**).
2. Registered system **`senderId`**; any assigned sender password if required by gateway configuration (the WSDL makes the password optional).
3. Official request XSD / XML sample for the selected interaction, plus allowable TEST data. **Do not** substitute the internal Nika `ISNA_DRAFT` JSON.
4. Transport signing procedure and approved GOST WS-Security signer connected to the registered certificate and its matching **private key**. A `.cer` file alone cannot sign.
5. Verify certificate suitability/validity/matching private key on the trusted machine. Keep private keys, passwords, and signed payloads outside GitHub and chat.

## Commands, TEST server only

```bash
cd /var/www/nika-business-test
sudo .venv/bin/python -m unittest discover -s tests -p test_isna_bip.py -v
sudo .venv/bin/python -m services.isna_bip --check-config
```

The `--check-config` command only prints safe readiness indicators. It sends no request.

When an **official XML service payload** and registered IDs are available, set the proper environment variables in the TEST deployment and build an *unsigned* SOAP envelope privately:

```bash
sudo .venv/bin/python -m services.isna_bip \
  --prepare-unsigned /private/path/official-request.xml \
  --output /private/path/isna-unsigned-soap.xml
```

This command only writes a new private (0600) file and **never sends it**; it refuses to overwrite an existing file. The file may contain `ISNA_BIP_PASSWORD` and sensitive filing data; protect it and remove it when finished.

### Transport settings

```text
APP_MODE=test
ISNA_BIP_URL=http://195.12.113.7/bip-sync-wss-gost/
ISNA_BIP_SERVICE_ID=<confirmed by Smart Bridge>
ISNA_BIP_SENDER_ID=<registered system ID>
ISNA_BIP_PASSWORD=<if assigned; optional in WSDL>
ISNA_BIP_SIGNER_COMMAND=<approved local/remote WS-Security GOST signer>
ISNA_BIP_SOAP_ACTION=     # blank => SOAPAction: "" in HTTP request
```

For SyncChannel v10, the operation is `SendMessage`, with `requestInfo` and `requestData/data`. The default request omits `sessionId`, which is assigned by BIP. Code does not yet implement or validate the transport GOST signature, nor map internal 910/200 JSON into official ISNA XML.

## Safety

No real/signed transmission until the official service specification, sender credentials, and signing implementation have been verified on TEST. The production branch and production database must remain unchanged.
