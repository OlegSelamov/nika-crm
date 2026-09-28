import json
import math
import os
import time
from datetime import datetime
from decimal import Decimal

import requests
from psycopg2.extras import Json

from models import get_db, pool


BINANCE_BASE_URL = os.getenv("CAPITAL_BINANCE_BASE_URL", "https://api.binance.com").rstrip("/")
DEFAULT_PAPER_BALANCE = Decimal(os.getenv("CAPITAL_PAPER_BALANCE", "10000"))
DEFAULT_SYMBOLS = tuple(
    s.strip().upper()
    for s in os.getenv("CAPITAL_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT").split(",")
    if s.strip()
)
ALLOWED_INTERVALS = {"15m", "30m", "1h", "2h", "4h"}
HTTP_TIMEOUT = float(os.getenv("CAPITAL_HTTP_TIMEOUT", "8"))


class CapitalLabError(RuntimeError):
    pass


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _validate_symbol(symbol):
    value = str(symbol or "").upper().strip()
    if value not in DEFAULT_SYMBOLS:
        raise CapitalLabError(
            "Пара недоступна в лаборатории. Разрешены: " + ", ".join(DEFAULT_SYMBOLS)
        )
    return value


def _validate_interval(interval):
    value = str(interval or "1h").strip()
    if value not in ALLOWED_INTERVALS:
        raise CapitalLabError("Недопустимый таймфрейм")
    return value


def _request_json(path, params=None):
    url = BINANCE_BASE_URL + path
    try:
        response = requests.get(
            url,
            params=params or {},
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": "NikaCapitalLab/0.1"},
        )
    except requests.RequestException as exc:
        raise CapitalLabError(f"Не удалось получить данные рынка: {exc}") from exc

    if response.status_code == 429:
        raise CapitalLabError("Binance временно ограничил частоту запросов. Повторите позже.")
    if response.status_code >= 400:
        raise CapitalLabError(
            f"Binance API вернул ошибку {response.status_code}: {response.text[:180]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise CapitalLabError("Binance API вернул некорректный ответ") from exc


def fetch_price(symbol):
    symbol = _validate_symbol(symbol)
    payload = _request_json("/api/v3/ticker/price", {"symbol": symbol})
    price = _float(payload.get("price"))
    if price <= 0:
        raise CapitalLabError("Не удалось определить текущую цену")
    return price


def fetch_24h(symbol):
    symbol = _validate_symbol(symbol)
    payload = _request_json("/api/v3/ticker/24hr", {"symbol": symbol})
    return {
        "symbol": symbol,
        "price": _float(payload.get("lastPrice")),
        "change_pct": _float(payload.get("priceChangePercent")),
        "high": _float(payload.get("highPrice")),
        "low": _float(payload.get("lowPrice")),
        "quote_volume": _float(payload.get("quoteVolume")),
    }


def fetch_klines(symbol, interval="1h", limit=120):
    symbol = _validate_symbol(symbol)
    interval = _validate_interval(interval)
    limit = max(60, min(int(limit or 120), 500))
    rows = _request_json(
        "/api/v3/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 11:
            continue
        result.append(
            {
                "open_time": int(row[0]),
                "open": _float(row[1]),
                "high": _float(row[2]),
                "low": _float(row[3]),
                "close": _float(row[4]),
                "volume": _float(row[5]),
                "close_time": int(row[6]),
                "quote_volume": _float(row[7]),
                "trades": int(row[8]),
                "taker_buy_volume": _float(row[9]),
            }
        )
    if len(result) < 60:
        raise CapitalLabError("Недостаточно рыночных данных для анализа")
    return result


def _ema(values, period):
    if not values:
        return 0.0
    period = max(2, int(period))
    multiplier = 2.0 / (period + 1.0)
    seed_count = min(period, len(values))
    current = sum(values[:seed_count]) / seed_count
    for value in values[seed_count:]:
        current = (value - current) * multiplier + current
    return current


def _rsi(values, period=14):
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for previous, current in zip(values[-(period + 1):-1], values[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return 0.0
    true_ranges = []
    start = max(1, len(closes) - period)
    for idx in range(start, len(closes)):
        true_ranges.append(
            max(
                highs[idx] - lows[idx],
                abs(highs[idx] - closes[idx - 1]),
                abs(lows[idx] - closes[idx - 1]),
            )
        )
    return sum(true_ranges) / max(len(true_ranges), 1)


def analyze_klines(klines):
    closes = [_float(row["close"]) for row in klines]
    highs = [_float(row["high"]) for row in klines]
    lows = [_float(row["low"]) for row in klines]
    volumes = [_float(row["volume"]) for row in klines]

    price = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)
    momentum_4 = ((price / closes[-5]) - 1.0) * 100.0 if closes[-5] else 0.0
    recent_volume = sum(volumes[-5:]) / 5.0
    baseline_slice = volumes[-25:-5]
    baseline_volume = sum(baseline_slice) / max(len(baseline_slice), 1)
    volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 1.0

    conditions = {
        "ema_trend": ema20 > ema50,
        "price_above_fast_ema": price > ema20,
        "rsi_zone": 46.0 <= rsi14 <= 68.0,
        "positive_momentum": momentum_4 > 0.0,
        "volume_ok": volume_ratio >= 0.85,
    }

    score = 25
    score += 20 if conditions["ema_trend"] else -10
    score += 15 if conditions["price_above_fast_ema"] else -8
    score += 15 if conditions["rsi_zone"] else -8
    score += 15 if conditions["positive_momentum"] else -8
    score += 10 if conditions["volume_ok"] else -5
    score = max(0, min(100, score))

    buy_ready = (
        conditions["ema_trend"]
        and conditions["price_above_fast_ema"]
        and conditions["rsi_zone"]
        and conditions["positive_momentum"]
        and score >= 70
    )

    stop_distance = max(atr14 * 1.6, price * 0.008)
    stop_price = max(0.00000001, price - stop_distance)
    take_price = price + (stop_distance * 2.0)
    risk_reward = (
        (take_price - price) / (price - stop_price)
        if price > stop_price
        else 0.0
    )

    reasons = []
    reasons.append(
        "EMA20 выше EMA50 — краткосрочный тренд направлен вверх"
        if conditions["ema_trend"]
        else "EMA20 не выше EMA50 — устойчивый восходящий тренд не подтверждён"
    )
    reasons.append(
        "Цена удерживается выше EMA20"
        if conditions["price_above_fast_ema"]
        else "Цена ниже EMA20"
    )
    reasons.append(f"RSI(14): {rsi14:.1f}")
    reasons.append(f"Импульс за 4 свечи: {momentum_4:+.2f}%")
    reasons.append(f"Относительный объём: {volume_ratio:.2f}x")

    return {
        "action": "BUY" if buy_ready else "WAIT",
        "score": int(score),
        "price": price,
        "stop_price": stop_price,
        "take_price": take_price,
        "risk_reward": risk_reward,
        "reasons": reasons,
        "indicators": {
            "ema20": ema20,
            "ema50": ema50,
            "rsi14": rsi14,
            "atr14": atr14,
            "momentum_4_pct": momentum_4,
            "volume_ratio": volume_ratio,
        },
    }


def build_market_signal(symbol, interval="1h"):
    symbol = _validate_symbol(symbol)
    interval = _validate_interval(interval)
    klines = fetch_klines(symbol, interval=interval, limit=120)
    analysis = analyze_klines(klines)
    ticker = fetch_24h(symbol)
    analysis.update(
        {
            "symbol": symbol,
            "interval": interval,
            "ticker_24h": ticker,
            "source": "binance_public_spot",
        }
    )
    return analysis


def calculate_position_size(
    equity,
    cash,
    entry_price,
    stop_price,
    risk_per_trade_pct,
    max_position_pct,
):
    equity = _float(equity)
    cash = _float(cash)
    entry_price = _float(entry_price)
    stop_price = _float(stop_price)
    risk_per_trade_pct = _float(risk_per_trade_pct)
    max_position_pct = _float(max_position_pct)

    if equity <= 0 or cash <= 0 or entry_price <= 0:
        raise CapitalLabError("Недостаточно виртуального капитала")
    if stop_price <= 0 or stop_price >= entry_price:
        raise CapitalLabError("Некорректный защитный стоп")

    stop_distance = entry_price - stop_price
    target_risk = equity * (risk_per_trade_pct / 100.0)
    quantity_by_risk = target_risk / stop_distance
    max_notional = min(cash, equity * (max_position_pct / 100.0))
    quantity_by_cap = max_notional / entry_price
    quantity = min(quantity_by_risk, quantity_by_cap)

    if quantity <= 0:
        raise CapitalLabError("Размер позиции получился нулевым")

    notional = quantity * entry_price
    actual_risk = quantity * stop_distance
    return {
        "quantity": quantity,
        "notional": notional,
        "risk_amount": actual_risk,
        "risk_pct": (actual_risk / equity * 100.0) if equity else 0.0,
    }


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS capital_accounts (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            mode TEXT NOT NULL DEFAULT 'paper',
            currency TEXT NOT NULL DEFAULT 'USDT',
            initial_balance NUMERIC(20,8) NOT NULL DEFAULT 10000,
            cash_balance NUMERIC(20,8) NOT NULL DEFAULT 10000,
            realized_pnl NUMERIC(20,8) NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(company_id, mode)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS capital_risk_limits (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL UNIQUE,
            risk_per_trade_pct NUMERIC(8,4) NOT NULL DEFAULT 0.5,
            max_daily_loss_pct NUMERIC(8,4) NOT NULL DEFAULT 1.5,
            max_position_pct NUMERIC(8,4) NOT NULL DEFAULT 25,
            max_open_positions INTEGER NOT NULL DEFAULT 2,
            min_risk_reward NUMERIC(8,4) NOT NULL DEFAULT 1.5,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS capital_signals (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            action TEXT NOT NULL,
            score INTEGER NOT NULL,
            entry_price NUMERIC(24,10) NOT NULL,
            stop_price NUMERIC(24,10) NOT NULL,
            take_price NUMERIC(24,10) NOT NULL,
            risk_reward NUMERIC(12,6) NOT NULL,
            reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            indicators JSONB NOT NULL DEFAULT '{}'::jsonb,
            market_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            executed_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_capital_signals_company_created
        ON capital_signals(company_id, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS capital_positions (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            signal_id BIGINT REFERENCES capital_signals(id),
            mode TEXT NOT NULL DEFAULT 'paper',
            symbol TEXT NOT NULL,
            side TEXT NOT NULL DEFAULT 'LONG',
            quantity NUMERIC(28,12) NOT NULL,
            entry_price NUMERIC(24,10) NOT NULL,
            stop_price NUMERIC(24,10) NOT NULL,
            take_price NUMERIC(24,10) NOT NULL,
            notional NUMERIC(20,8) NOT NULL,
            risk_amount NUMERIC(20,8) NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            exit_price NUMERIC(24,10),
            pnl NUMERIC(20,8),
            close_reason TEXT,
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_capital_positions_company_status
        ON capital_positions(company_id, status, opened_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS capital_trade_events (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            position_id BIGINT REFERENCES capital_positions(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            price NUMERIC(24,10),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _ensure_defaults(cur, company_id):
    cur.execute(
        """
        INSERT INTO capital_accounts (
            company_id, mode, currency, initial_balance, cash_balance
        )
        VALUES (%s, 'paper', 'USDT', %s, %s)
        ON CONFLICT (company_id, mode) DO NOTHING
        """,
        (company_id, DEFAULT_PAPER_BALANCE, DEFAULT_PAPER_BALANCE),
    )
    cur.execute(
        """
        INSERT INTO capital_risk_limits (company_id)
        VALUES (%s)
        ON CONFLICT (company_id) DO NOTHING
        """,
        (company_id,),
    )


def _with_schema(company_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        ensure_schema(cur)
        _ensure_defaults(cur, company_id)
        conn.commit()
    except Exception:
        conn.rollback()
        cur.close()
        pool.putconn(conn)
        raise
    return conn, cur


def create_signal(company_id, symbol, interval="1h"):
    signal = build_market_signal(symbol, interval)
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            INSERT INTO capital_signals (
                company_id, symbol, interval, action, score,
                entry_price, stop_price, take_price, risk_reward,
                reasons, indicators, market_snapshot
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                company_id,
                signal["symbol"],
                signal["interval"],
                signal["action"],
                signal["score"],
                signal["price"],
                signal["stop_price"],
                signal["take_price"],
                signal["risk_reward"],
                Json(signal["reasons"]),
                Json(signal["indicators"]),
                Json(signal["ticker_24h"]),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        signal["id"] = row["id"]
        signal["created_at"] = row["created_at"].isoformat()
        signal["status"] = "pending"
        return signal
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _daily_loss(cur, company_id):
    cur.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN pnl < 0 THEN -pnl ELSE 0 END), 0) AS loss
        FROM capital_positions
        WHERE company_id = %s
          AND status = 'closed'
          AND DATE(closed_at AT TIME ZONE 'Asia/Almaty')
              = DATE(NOW() AT TIME ZONE 'Asia/Almaty')
        """,
        (company_id,),
    )
    row = cur.fetchone() or {}
    return _float(row.get("loss"))


def open_paper_position(company_id, signal_id):
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            SELECT *
            FROM capital_signals
            WHERE id = %s AND company_id = %s
            FOR UPDATE
            """,
            (signal_id, company_id),
        )
        signal = cur.fetchone()
        if not signal:
            raise CapitalLabError("Сигнал не найден")
        if signal["status"] != "pending":
            raise CapitalLabError("Этот сигнал уже обработан")
        if signal["action"] != "BUY":
            raise CapitalLabError("Сигнал WAIT нельзя открыть как сделку")

        current_price = fetch_price(signal["symbol"])
        planned_entry = _float(signal["entry_price"])
        if planned_entry <= 0:
            raise CapitalLabError("Некорректная цена сигнала")
        slippage_pct = abs(current_price - planned_entry) / planned_entry * 100.0
        if slippage_pct > 1.2:
            raise CapitalLabError(
                f"Сигнал устарел: цена ушла на {slippage_pct:.2f}%. Создайте новый анализ."
            )

        cur.execute(
            """
            SELECT *
            FROM capital_accounts
            WHERE company_id = %s AND mode = 'paper'
            FOR UPDATE
            """,
            (company_id,),
        )
        account = cur.fetchone()
        cur.execute(
            "SELECT * FROM capital_risk_limits WHERE company_id = %s",
            (company_id,),
        )
        limits = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(notional), 0) AS open_cost
            FROM capital_positions
            WHERE company_id = %s AND status = 'open'
            """,
            (company_id,),
        )
        open_summary = cur.fetchone() or {}
        open_count = int(open_summary.get("cnt") or 0)
        if open_count >= int(limits["max_open_positions"]):
            raise CapitalLabError("Достигнут лимит одновременно открытых позиций")

        cash = _float(account["cash_balance"])
        open_cost = _float(open_summary.get("open_cost"))
        equity_at_cost = cash + open_cost
        daily_loss = _daily_loss(cur, company_id)
        daily_loss_limit = equity_at_cost * _float(limits["max_daily_loss_pct"]) / 100.0
        if daily_loss_limit > 0 and daily_loss >= daily_loss_limit:
            raise CapitalLabError("Достигнут дневной лимит убытка. Новые сделки заблокированы.")

        original_stop_distance = planned_entry - _float(signal["stop_price"])
        if original_stop_distance <= 0:
            raise CapitalLabError("Стоп сигнала рассчитан некорректно")
        stop_price = current_price - original_stop_distance
        original_take_distance = _float(signal["take_price"]) - planned_entry
        take_price = current_price + max(original_take_distance, original_stop_distance * 1.5)
        risk_reward = (take_price - current_price) / (current_price - stop_price)
        if risk_reward < _float(limits["min_risk_reward"]):
            raise CapitalLabError("Соотношение риск/прибыль ниже установленного минимума")

        sizing = calculate_position_size(
            equity_at_cost,
            cash,
            current_price,
            stop_price,
            limits["risk_per_trade_pct"],
            limits["max_position_pct"],
        )
        if sizing["notional"] < 10:
            raise CapitalLabError("Размер позиции меньше 10 USDT")

        cur.execute(
            """
            INSERT INTO capital_positions (
                company_id, signal_id, mode, symbol, side, quantity,
                entry_price, stop_price, take_price, notional, risk_amount
            )
            VALUES (%s, %s, 'paper', %s, 'LONG', %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                company_id,
                signal_id,
                signal["symbol"],
                sizing["quantity"],
                current_price,
                stop_price,
                take_price,
                sizing["notional"],
                sizing["risk_amount"],
            ),
        )
        position = cur.fetchone()

        cur.execute(
            """
            UPDATE capital_accounts
            SET cash_balance = cash_balance - %s,
                updated_at = NOW()
            WHERE company_id = %s AND mode = 'paper'
            """,
            (sizing["notional"], company_id),
        )
        cur.execute(
            """
            UPDATE capital_signals
            SET status = 'executed', executed_at = NOW()
            WHERE id = %s
            """,
            (signal_id,),
        )
        cur.execute(
            """
            INSERT INTO capital_trade_events (
                company_id, position_id, event_type, price, payload
            )
            VALUES (%s, %s, 'OPEN', %s, %s)
            """,
            (
                company_id,
                position["id"],
                current_price,
                Json(
                    {
                        "paper": True,
                        "signal_score": signal["score"],
                        "risk_pct": sizing["risk_pct"],
                    }
                ),
            ),
        )
        conn.commit()
        return _serialize_position(position, mark_price=current_price)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def skip_signal(company_id, signal_id):
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            UPDATE capital_signals
            SET status = 'skipped'
            WHERE id = %s AND company_id = %s AND status = 'pending'
            RETURNING id
            """,
            (signal_id, company_id),
        )
        row = cur.fetchone()
        if not row:
            raise CapitalLabError("Сигнал уже обработан или не найден")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def _close_position_locked(cur, company_id, position, exit_price, reason):
    quantity = _float(position["quantity"])
    entry_price = _float(position["entry_price"])
    proceeds = quantity * exit_price
    pnl = (exit_price - entry_price) * quantity

    cur.execute(
        """
        UPDATE capital_positions
        SET status = 'closed',
            exit_price = %s,
            pnl = %s,
            close_reason = %s,
            closed_at = NOW()
        WHERE id = %s AND company_id = %s AND status = 'open'
        RETURNING *
        """,
        (exit_price, pnl, reason, position["id"], company_id),
    )
    closed = cur.fetchone()
    if not closed:
        return None

    cur.execute(
        """
        UPDATE capital_accounts
        SET cash_balance = cash_balance + %s,
            realized_pnl = realized_pnl + %s,
            updated_at = NOW()
        WHERE company_id = %s AND mode = 'paper'
        """,
        (proceeds, pnl, company_id),
    )
    cur.execute(
        """
        INSERT INTO capital_trade_events (
            company_id, position_id, event_type, price, payload
        )
        VALUES (%s, %s, 'CLOSE', %s, %s)
        """,
        (
            company_id,
            position["id"],
            exit_price,
            Json({"paper": True, "reason": reason, "pnl": pnl}),
        ),
    )
    return closed


def close_paper_position(company_id, position_id, reason="manual"):
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            SELECT *
            FROM capital_positions
            WHERE id = %s AND company_id = %s
            FOR UPDATE
            """,
            (position_id, company_id),
        )
        position = cur.fetchone()
        if not position:
            raise CapitalLabError("Позиция не найдена")
        if position["status"] != "open":
            raise CapitalLabError("Позиция уже закрыта")
        exit_price = fetch_price(position["symbol"])
        closed = _close_position_locked(cur, company_id, position, exit_price, reason)
        conn.commit()
        return _serialize_position(closed, mark_price=exit_price)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def sync_open_positions(company_id):
    conn, cur = _with_schema(company_id)
    closed_items = []
    try:
        cur.execute(
            """
            SELECT *
            FROM capital_positions
            WHERE company_id = %s AND status = 'open'
            ORDER BY opened_at
            """,
            (company_id,),
        )
        positions = cur.fetchall() or []
        price_cache = {}
        for position in positions:
            symbol = position["symbol"]
            if symbol not in price_cache:
                price_cache[symbol] = fetch_price(symbol)

        for position in positions:
            price = price_cache[position["symbol"]]
            stop_price = _float(position["stop_price"])
            take_price = _float(position["take_price"])
            reason = None
            if price <= stop_price:
                reason = "stop_loss"
            elif price >= take_price:
                reason = "take_profit"
            if not reason:
                continue

            cur.execute(
                """
                SELECT *
                FROM capital_positions
                WHERE id = %s AND company_id = %s
                FOR UPDATE
                """,
                (position["id"], company_id),
            )
            locked = cur.fetchone()
            if not locked or locked["status"] != "open":
                continue
            closed = _close_position_locked(cur, company_id, locked, price, reason)
            if closed:
                closed_items.append(_serialize_position(closed, mark_price=price))

        conn.commit()
        return closed_items
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def sync_all_open_positions():
    conn = get_db()
    cur = conn.cursor()
    try:
        ensure_schema(cur)
        conn.commit()
        cur.execute(
            """
            SELECT DISTINCT company_id
            FROM capital_positions
            WHERE status = 'open'
            """
        )
        company_ids = [int(row["company_id"]) for row in (cur.fetchall() or [])]
    finally:
        cur.close()
        pool.putconn(conn)

    total_closed = 0
    errors = []
    for company_id in company_ids:
        try:
            total_closed += len(sync_open_positions(company_id))
        except Exception as exc:
            errors.append({"company_id": company_id, "error": str(exc)})
    return {"companies": len(company_ids), "closed": total_closed, "errors": errors}


def _serialize_signal(row):
    return {
        "id": int(row["id"]),
        "symbol": row["symbol"],
        "interval": row["interval"],
        "action": row["action"],
        "score": int(row["score"]),
        "entry_price": _float(row["entry_price"]),
        "stop_price": _float(row["stop_price"]),
        "take_price": _float(row["take_price"]),
        "risk_reward": _float(row["risk_reward"]),
        "reasons": row.get("reasons") or [],
        "indicators": row.get("indicators") or {},
        "market_snapshot": row.get("market_snapshot") or {},
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "executed_at": row["executed_at"].isoformat() if row.get("executed_at") else None,
    }


def _serialize_position(row, mark_price=None):
    if not row:
        return None
    entry = _float(row["entry_price"])
    quantity = _float(row["quantity"])
    mark = _float(mark_price if mark_price is not None else row.get("exit_price") or entry)
    unrealized = (mark - entry) * quantity if row["status"] == "open" else 0.0
    return {
        "id": int(row["id"]),
        "signal_id": int(row["signal_id"]) if row.get("signal_id") else None,
        "symbol": row["symbol"],
        "side": row["side"],
        "quantity": quantity,
        "entry_price": entry,
        "stop_price": _float(row["stop_price"]),
        "take_price": _float(row["take_price"]),
        "notional": _float(row["notional"]),
        "risk_amount": _float(row["risk_amount"]),
        "status": row["status"],
        "mark_price": mark,
        "unrealized_pnl": unrealized,
        "exit_price": _float(row["exit_price"]) if row.get("exit_price") is not None else None,
        "pnl": _float(row["pnl"]) if row.get("pnl") is not None else None,
        "close_reason": row.get("close_reason"),
        "opened_at": row["opened_at"].isoformat() if row.get("opened_at") else None,
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
    }


def get_overview(company_id):
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            "SELECT * FROM capital_accounts WHERE company_id = %s AND mode = 'paper'",
            (company_id,),
        )
        account = cur.fetchone()
        cur.execute(
            "SELECT * FROM capital_risk_limits WHERE company_id = %s",
            (company_id,),
        )
        limits = cur.fetchone()
        cur.execute(
            """
            SELECT *
            FROM capital_signals
            WHERE company_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (company_id,),
        )
        signals = cur.fetchall() or []
        cur.execute(
            """
            SELECT *
            FROM capital_positions
            WHERE company_id = %s
            ORDER BY opened_at DESC
            LIMIT 100
            """,
            (company_id,),
        )
        positions = cur.fetchall() or []
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'closed') AS closed_count,
                COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0) AS wins,
                COALESCE(SUM(pnl) FILTER (WHERE status = 'closed'), 0) AS total_pnl,
                COALESCE(AVG(pnl) FILTER (WHERE status = 'closed' AND pnl > 0), 0) AS avg_win,
                COALESCE(AVG(ABS(pnl)) FILTER (WHERE status = 'closed' AND pnl < 0), 0) AS avg_loss
            FROM capital_positions
            WHERE company_id = %s
            """,
            (company_id,),
        )
        stats = cur.fetchone() or {}
    finally:
        cur.close()
        pool.putconn(conn)

    price_cache = {}
    serialized_positions = []
    unrealized_total = 0.0
    for position in positions:
        mark = None
        if position["status"] == "open":
            symbol = position["symbol"]
            try:
                if symbol not in price_cache:
                    price_cache[symbol] = fetch_price(symbol)
                mark = price_cache[symbol]
            except Exception:
                mark = _float(position["entry_price"])
        item = _serialize_position(position, mark_price=mark)
        serialized_positions.append(item)
        unrealized_total += item["unrealized_pnl"]

    cash = _float(account["cash_balance"])
    open_market_value = sum(
        item["quantity"] * item["mark_price"]
        for item in serialized_positions
        if item["status"] == "open"
    )
    equity = cash + open_market_value
    closed_count = int(stats.get("closed_count") or 0)
    wins = int(stats.get("wins") or 0)
    avg_loss = _float(stats.get("avg_loss"))
    avg_win = _float(stats.get("avg_win"))
    profit_factor_proxy = (avg_win / avg_loss) if avg_loss > 0 else None

    return {
        "mode": "paper",
        "symbols": list(DEFAULT_SYMBOLS),
        "intervals": sorted(ALLOWED_INTERVALS),
        "account": {
            "currency": account["currency"],
            "initial_balance": _float(account["initial_balance"]),
            "cash_balance": cash,
            "realized_pnl": _float(account["realized_pnl"]),
            "unrealized_pnl": unrealized_total,
            "equity": equity,
        },
        "risk": {
            "risk_per_trade_pct": _float(limits["risk_per_trade_pct"]),
            "max_daily_loss_pct": _float(limits["max_daily_loss_pct"]),
            "max_position_pct": _float(limits["max_position_pct"]),
            "max_open_positions": int(limits["max_open_positions"]),
            "min_risk_reward": _float(limits["min_risk_reward"]),
            "daily_loss": _daily_loss_for_overview(company_id),
        },
        "stats": {
            "closed_count": closed_count,
            "wins": wins,
            "win_rate": (wins / closed_count * 100.0) if closed_count else 0.0,
            "total_pnl": _float(stats.get("total_pnl")),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor_proxy": profit_factor_proxy,
        },
        "signals": [_serialize_signal(row) for row in signals],
        "positions": serialized_positions,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def _daily_loss_for_overview(company_id):
    conn, cur = _with_schema(company_id)
    try:
        return _daily_loss(cur, company_id)
    finally:
        cur.close()
        pool.putconn(conn)


def update_risk_limits(company_id, payload):
    fields = {
        "risk_per_trade_pct": float(payload.get("risk_per_trade_pct")),
        "max_daily_loss_pct": float(payload.get("max_daily_loss_pct")),
        "max_position_pct": float(payload.get("max_position_pct")),
        "max_open_positions": int(payload.get("max_open_positions")),
        "min_risk_reward": float(payload.get("min_risk_reward")),
    }
    if not (0.05 <= fields["risk_per_trade_pct"] <= 2.0):
        raise CapitalLabError("Риск на сделку должен быть от 0.05% до 2%")
    if not (0.25 <= fields["max_daily_loss_pct"] <= 5.0):
        raise CapitalLabError("Дневной лимит должен быть от 0.25% до 5%")
    if not (5.0 <= fields["max_position_pct"] <= 50.0):
        raise CapitalLabError("Максимальный размер позиции должен быть от 5% до 50%")
    if not (1 <= fields["max_open_positions"] <= 5):
        raise CapitalLabError("Разрешено от 1 до 5 открытых позиций")
    if not (1.0 <= fields["min_risk_reward"] <= 5.0):
        raise CapitalLabError("Минимальный Risk/Reward должен быть от 1 до 5")

    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            UPDATE capital_risk_limits
            SET risk_per_trade_pct = %s,
                max_daily_loss_pct = %s,
                max_position_pct = %s,
                max_open_positions = %s,
                min_risk_reward = %s,
                updated_at = NOW()
            WHERE company_id = %s
            """,
            (
                fields["risk_per_trade_pct"],
                fields["max_daily_loss_pct"],
                fields["max_position_pct"],
                fields["max_open_positions"],
                fields["min_risk_reward"],
                company_id,
            ),
        )
        conn.commit()
        return fields
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def reset_paper_account(company_id):
    conn, cur = _with_schema(company_id)
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM capital_positions
            WHERE company_id = %s AND status = 'open'
            """,
            (company_id,),
        )
        if int((cur.fetchone() or {}).get("cnt") or 0) > 0:
            raise CapitalLabError("Сначала закройте все виртуальные позиции")

        cur.execute(
            "DELETE FROM capital_trade_events WHERE company_id = %s",
            (company_id,),
        )
        cur.execute(
            "DELETE FROM capital_positions WHERE company_id = %s",
            (company_id,),
        )
        cur.execute(
            "DELETE FROM capital_signals WHERE company_id = %s",
            (company_id,),
        )
        cur.execute(
            """
            UPDATE capital_accounts
            SET cash_balance = initial_balance,
                realized_pnl = 0,
                updated_at = NOW()
            WHERE company_id = %s AND mode = 'paper'
            """,
            (company_id,),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
