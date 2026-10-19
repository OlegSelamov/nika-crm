-- Manual reconciliation for 19 Oct 2026 POS charge / reKassa receipt.
-- RUN ONLY AFTER the code supporting manual_fiscalized_at is deployed.
-- Do not re-fiscalize or call process_sale: stock was already consumed.
-- Safe to run repeatedly; updates exactly one expected paid invoice.
\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    row_before RECORD;
BEGIN
    SELECT id, sale_type, status, total_amount, paid_amount, is_processed
    INTO row_before
    FROM sales
    WHERE id = 842 AND company_id = 16 AND sale_number = 575
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sale 842 / company 16 / number 575 not found';
    END IF;
    IF row_before.total_amount <> 9350 OR row_before.paid_amount <> 9350
       OR row_before.status <> 'Оплачено' OR row_before.is_processed IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'Sale values / stock processing do not match documented payment';
    END IF;
    IF row_before.sale_type NOT IN ('invoice', 'kaspi') THEN
        RAISE EXCEPTION 'Unexpected sale type: %', row_before.sale_type;
    END IF;

    -- Mark manually fiscalized BEFORE converting invoice to POS sale, so the
    -- duplicate-prevention guards see the marker if retried afterwards.
    UPDATE sales
    SET manual_fiscalized_at = '2026-10-19 19:56:33'::timestamp,
        manual_fiscal_receipt_url =
          'https://ofd.rekassa.kz/t/?i=270766593555&f=181604888682&s=9350&t=20261019T195633',
        manual_fiscal_note =
          'Receipt #26; shift #19; RNM 181604888682; ZNM YTRAW8Z5-GKN; manually issued 2026-10-19 19:56:33; original POS charge around 17:36:37',
        sale_type = 'kaspi',
        kaspi_amount = 9350,
        card_amount = 0,
        cash_amount = 0,
        rekassa_ticket_number = '270766593555',
        rekassa_document_number = 26,
        rekassa_shift_number = 19,
        rekassa_rnm = '181604888682',
        rekassa_znm = 'YTRAW8Z5-GKN',
        rekassa_qr =
          'https://ofd.rekassa.kz/t/?i=270766593555&f=181604888682&s=9350&t=20261019T195633',
        rekassa_status = 'MANUAL',
        fiscal_provider = 'rekassa',
        fiscal_status = 'fiscalized',
        fiscal_ticket_number = '270766593555',
        fiscal_shift_number = '19'
    WHERE id = 842 AND company_id = 16 AND sale_number = 575;

    -- The original bank transaction ID is unavailable; do not fabricate it.
    -- The internal reKassa ticket ID is also unknown; do not put the fiscal
    -- sign or ticket #26 in that numeric API identifier column.
END $$;

SELECT
    id, company_id, sale_number, sale_type, status, total_amount,
    paid_amount, kaspi_amount, card_amount, is_processed,
    rekassa_ticket_id, rekassa_ticket_number, rekassa_shift_number,
    manual_fiscalized_at, manual_fiscal_receipt_url
FROM sales WHERE id = 842 AND company_id = 16;

-- Verify result above. Execute COMMIT manually when satisfied.
-- If anything differs, execute ROLLBACK.
