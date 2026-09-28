import math

from services.capital_lab import analyze_klines, calculate_position_size


def _trend_klines(count=120, start=100.0, step=0.35):
    rows = []
    price = start
    for idx in range(count):
        open_price = price
        close_price = price + step
        high = close_price + 0.25
        low = open_price - 0.20
        volume = 1000 + idx * 3
        rows.append(
            {
                "open_time": idx,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": volume,
                "close_time": idx + 1,
                "quote_volume": volume * close_price,
                "trades": 100,
                "taker_buy_volume": volume * 0.55,
            }
        )
        price = close_price
    return rows


def test_position_sizing_respects_risk_limit():
    result = calculate_position_size(
        equity=10000,
        cash=10000,
        entry_price=100,
        stop_price=98,
        risk_per_trade_pct=0.5,
        max_position_pct=25,
    )
    assert math.isclose(result["risk_amount"], 50.0, rel_tol=1e-9)
    assert result["notional"] <= 2500.0 + 1e-9
    assert result["risk_pct"] <= 0.5 + 1e-9


def test_position_sizing_respects_position_cap():
    result = calculate_position_size(
        equity=10000,
        cash=10000,
        entry_price=100,
        stop_price=99.9,
        risk_per_trade_pct=2.0,
        max_position_pct=10,
    )
    assert math.isclose(result["notional"], 1000.0, rel_tol=1e-9)
    assert result["risk_amount"] < 200.0


def test_analyzer_produces_bounded_score_and_protective_levels():
    result = analyze_klines(_trend_klines())
    assert 0 <= result["score"] <= 100
    assert result["price"] > result["stop_price"]
    assert result["take_price"] > result["price"]
    assert result["risk_reward"] >= 1.5
    assert result["action"] in {"BUY", "WAIT"}


def test_analyzer_waits_on_flat_weak_market():
    rows = _trend_klines(step=0.0)
    for idx, row in enumerate(rows):
        row["close"] = 100.0 - ((idx % 5) * 0.05)
        row["open"] = row["close"] + 0.03
        row["high"] = row["open"] + 0.05
        row["low"] = row["close"] - 0.05
        row["volume"] = 800
    result = analyze_klines(rows)
    assert result["action"] == "WAIT"
