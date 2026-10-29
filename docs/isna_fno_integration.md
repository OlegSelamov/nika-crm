# FNO_INTEGRATION: TEST-only SOAP contract and offline development

## Source evidence

Analyzed the user-supplied provider artifacts on 2026-10-29. They are *not*
committed: the sample XML contains third-party identifiers, a sample password,
and an already-signed declaration.

- `fno-integration-request-vshep.xml`: SOAP 1.1 SyncChannel v10
  `SendMessage` with `serviceId=FNO_INTEGRATION`. Inside `requestData`,
  the `data` element has `xsi:type="xs:string"`, **not** an embedded XML
  node. Its decoded text is a second XML document, where `root/data`
  contains JSON and an enveloped `ds:Signature` belongs to the taxpayer.
  The provided example has malformed inner CDATA after decoding; **do not
  submit or re-sign it**. A published sample password and `senderId` are
  examples, **not** credentials issued to Nika Business.
- `FNO_INTEGRATION_RESPONSE_ (3).xml`: SOAP `SendMessageResponse` with
  `responseInfo/status/code=OK`, plus a JSON string in
  `responseData/data` containing `success=true` and `fno_id`.
  The sample is **not evidence of a Nika Business submission**.
- `declareRequestResponseTypes.xsd`: namespace `http://smartbridge.b10.kz`;
  defines **two top-level string elements**, `sendMessageRequest` and
  `sendMessageResponse`. It is *not* the complete taxpayer declaration
  validation XSD or the SyncChannel WSDL.

## Implemented in the test branch

- `services/isna_bip.py` now supports `data_encoding="string"` alongside
  the legacy `data_encoding="xml"`. In string mode it puts the separately
  signed XML into `<data xsi:type="xs:string">escaped XML text</data>`.
  Escaping is semantically the same as CDATA in SOAP XML; no untrusted
  `<![CDATA[` boundary manipulation is needed.
- `services/isna_fno_integration.py` provides:
  - `inspect_taxpayer_signed_fno(xml)`: **structural only** XML/JSON/XMLDSig
    validation; it does **NOT** cryptographically verify the taxpayer EDS.
  - `build_fno_integration_soap(xml, sender_id, sender_password="")`:
    builds an **unsigned** transport SOAP envelope with the official string
    representation; blocks the sample `senderId=smartbridge`.
  - `parse_fno_integration_response(xml)`: parses SOAP Faults and the
    business response. `ok=True` requires both transport status `OK`
    **and** inner JSON `success=true`; HTTP 200 alone is not success.
- Existing CLI `python -m services.isna_bip --prepare-unsigned ...`
  automatically routes FNO_INTEGRATION through the specialized adapter.
- `tests/test_isna_fno_integration.py` exercises positive cases, malformed
  input, sample-sender rejection, SOAP faults, success interpretation,
  export file permissions and **no outbound network calls**.

Nothing here transmits tax forms, stores taxpayer secrets in GitHub, or
deploys to the production system.

## Offline smoke test

Run only in a secure TEST workspace using a **properly taxpayer-signed**
FNO XML stored privately (not the provider's malformed demo). The existing
CLI requires verified `ISNA_BIP_SERVICE_ID=FNO_INTEGRATION` and an assigned
`ISNA_BIP_SENDER_ID` in the TEST-only environment.

```bash
cd /var/www/nika-business-test
sudo -u www-data .venv/bin/python -m unittest discover \
  -s tests -p 'test_isna_fno_integration.py' -v
sudo -u www-data .venv/bin/python -m services.isna_bip --check-config
```

For a properly taxpayer-signed, locally stored private sample (never use
the downloaded provider demo):

```bash
# Keep input and output outside of any web-served directory.
.venv/bin/python -m services.isna_bip \
  --prepare-unsigned /secure/isna/validated-signed-fno.xml \
  --output /secure/isna/unsigned-soap.xml
```

The output mode is 0600 and the script refuses to overwrite an existing
file. **This command NEVER sends SOAP**.

## Next essential work before the first TEST POST

1. Verify that the user-accessible `senderId` equals the identifier
   registered for Nika Business (the portal login is a candidate, **not yet
   confirmed**). Configure the TEST password privately if required.
2. Obtain the full provider schema/instructions for the form-specific JSON
   `fnoDto`, starting with the intended 200.00 or 910.00 version. The
   generic `declareRequestResponseTypes.xsd` alone does not specify
   those tax fields. Never fabricate mandatory FNO values.
3. Prepare the taxpayer's actual declaration and validate the *inner*
   XMLDSig with KalkanCrypt or a trusted independent verifier. The
   existing Android demo transport key is **not** a universal taxpayer
   signing authority for arbitrary tenants.
4. Integrate production-quality **outer** WS-Security GOST signing for an
   actual `SendMessage` envelope, including source XML integrity and
   independent verification. The existing Android test signs only a
   synthetic SOAP document and does not send it.
5. Only with approved TEST credentials, authorized taxpayer signing and
   validated schema, add an explicitly enabled submission path with
   idempotency, messageId correlation, encrypted audit data, and safe
   handling of SOAP faults. Start with a non-filing TEST action if the
   provider supplies an authorized one.

The existing Android "Отправить в ИСНА" button **remains disabled**.
