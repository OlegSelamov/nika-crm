# ISNA real FNO 200.00 / 910.00 — first Android taxpayer signature

This implementation is separate from **synthetic** FNO 000.00 tests.

## Preparing the official declaration

In the actual tax cabinet, select the authorized organization's profile,
complete the correct form and period, review the identifying fields and figures.
Do not file the form in the cabinet when the purpose is to test Nika's filing
process (to avoid an accidental duplicate).

The KGD official guidance on obtaining form data is:
https://www.gov.kz/org/kgd/press/article/details/233841?lang=ru
(Question 3: Developer Tools / Console / last `Values object` / Copy object).
**Important:** a copied browser `Values object` is NOT automatically the
`fnoDto` data contract for the FNO_INTEGRATION service. Check the
service-specific JSON schema and resulting full `code` + `fnoDto` object
before signing. We fail closed rather than invent a mapping.

The mobile signer accepts exactly this *service request representation*:

```json
{
  "code": "910.00",
  "fnoDto": {
    "OFFICIAL_FIELDS_ONLY": "example not a declaration"
  }
}
```

The above is purely an **illustration of nesting**, NOT a real form.
Never submit or sign an illustrative DTO. No exact form field mapping was
claimed or fabricated here. Select 910.00 or 200.00 according to the form
and the taxpayer's applicable reporting obligations.

## Android TEST workflow (no outbound FNO transmission)

1. Open **ИСНА · тестирование** in the isolated Nika Android TEST app.
2. Click **Подписать настоящую ФНО 910/200 · локально**.
3. Choose the same form code that appears in the official completed JSON.
4. Paste the full official `{"code":"...","fnoDto":{...}}` request, not
   guessed tax fields. The app builds an unsigned `root/data` XML locally.
5. Confirm the data and authorization, select the actual **taxpayer's**
   signing P12, and enter the password only on Android.
6. Kotlin verifies the input XML, runs local Kalkan XMLDSig signing and
   **verifies the final serialized signature with the selected X509
   certificate** before returning the result. Neither original JSON
   nor private P12 is sent to a Nika server during this operation.
7. Click **Сохранить подписанный XML**. Store it securely because it
   contains sensitive tax data. The selected file name begins
   `nika-isna-real-fno-910-00-signed.xml` (or `200-00`).

An XMLDSig verification means the **bits** were signed by the matching
private key. It does not by itself prove Smart Bridge registration,
taxpayer organization/representative authorization, tax-form correctness,
or acceptance by IСНА.

## Next step: one controlled TEST gateway POST

After verifying the signed content and its signer, transfer the signed
XML only through an operator-approved secure channel to the private TEST
signer OS account (outside `/var/www`, owner-only access).
The already deployed server CLI:
`services/isna_real_fno_submission.py` has a real, opt-in
`FNO_INTEGRATION` POST. It requires independent GOST verification of
the taxpayer's signature, a registered Nika **transport** certificate
and separate system P12, a private deduplication journal, and explicit
one-shot consent. See `docs/isna_real_fno_test_submission.md`.

It is **not** the disabled legacy Android button `Отправить в ИСНА`;
and it does not submit anything automatically or target PROD.
