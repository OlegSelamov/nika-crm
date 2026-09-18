@settings_bp.route("/api/integrations/alatau/accounts")
def alatau_accounts():
    company_id, error = _alatau_current_company()
    if error:
        return error

    environment = (request.args.get("environment") or "test").strip().lower()
    try:
        client, access_token, bank_company_id, environment = _alatau_live_session(
            company_id, environment
        )
        try:
            payload = client.get_accounts(access_token, bank_company_id)
            endpoint = "v1"
        except AlatauError as first_exc:
            if first_exc.status_code not in (400, 404):
                raise
            payload = client.get_accounts_cards(access_token, bank_company_id)
            endpoint = "v3"

        if isinstance(payload, list):
            accounts = payload
        elif isinstance(payload, dict):
            accounts = payload.get("accounts") or payload.get("data") or payload.get("items")
            if accounts is None and payload.get("iban"):
                accounts = [payload]
            accounts = accounts or []
        else:
            accounts = []

        # Банк и БИК берём из справочника самого Alatau. Если справочник
        # временно недоступен, оставляем безопасный fallback для текущей интеграции.
        bank_info = {
            "name": "Alatau City Bank",
            "bic": "TSESKZKA",
        }
        try:
            bank_rows = client.get_banks(access_token)
            if isinstance(bank_rows, dict):
                bank_rows = (
                    bank_rows.get("content")
                    or bank_rows.get("items")
                    or bank_rows.get("data")
                    or bank_rows.get("banks")
                    or []
                )
            if isinstance(bank_rows, list):
                preferred = None
                for bank in bank_rows:
                    if not isinstance(bank, dict):
                        continue
                    bic = str(
                        bank.get("bic")
                        or bank.get("bankBic")
                        or bank.get("code")
                        or ""
                    ).replace(" ", "").upper()
                    name = str(
                        bank.get("name")
                        or bank.get("bankName")
                        or bank.get("fullName")
                        or ""
                    ).strip()
                    if bic == "TSESKZKA":
                        preferred = {"name": name or "Alatau City Bank", "bic": bic}
                        break
                    if not preferred and "ALATAU" in name.upper():
                        preferred = {"name": name, "bic": bic or "TSESKZKA"}
                if preferred:
                    bank_info = preferred
        except AlatauError:
            pass

        _alatau_touch(
            company_id,
            environment,
            bank_company_id=bank_company_id,
            error=None,
        )
        company_requisites = {}
        req_conn = get_db()
        try:
            req_cur = req_conn.cursor()
            req_cur.execute("""
                SELECT name, address, bin, kbe
                FROM companies
                WHERE id = %s
                LIMIT 1
            """, (company_id,))
            req_row = req_cur.fetchone()
            company_requisites = dict(req_row) if req_row else {}
        finally:
            pool.putconn(req_conn)

        return jsonify({
            "success": True,
            "environment": environment,
            "company_id": bank_company_id,
            "endpoint": endpoint,
            "accounts": accounts,
            "bank": bank_info,
            "company": company_requisites,
        })
    except AlatauError as exc:
        _alatau_touch(company_id, environment, error=str(exc)[:500])
        return jsonify({"success": False, "error": str(exc)}), exc.status_code


