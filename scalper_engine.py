"""
MEXC Scalping Strategy Engine — Python Standalone
==================================================
Run locally for: backtesting, signal logging, automation
Strategy: EMA(9,21) + RSI(14) + VWAP + Volume
Timeframe: 1m / 5m
Exchange: MEXC (public REST, no API key needed for market data)

Install: pip install requests pandas numpy colorama
Run:     python scalper_engine.py
"""

import requests
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
MEXC_REST = "https://api.mexc.com/api/v3"

WATCHLIST = [
    "SOLUSDT", "DOGEUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT",
    "MATICUSDT", "DOTUSDT", "ADAUSDT", "LTCUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
]

STRATEGY = {
    "ema_fast": 9,
    "ema_slow": 21,
    "rsi_period": 14,
    "vol_avg_period": 20,
    "atr_period": 14,
    # Entry thresholds
    "min_signal_strength": 70,       # out of 100
    "vol_ratio_threshold": 1.5,      # volume spike minimum
    "rsi_long_min": 45,
    "rsi_long_max": 65,
    "rsi_short_min": 35,
    "rsi_short_max": 55,
    # Risk filters
    "rsi_overbought": 75,
    "rsi_oversold": 25,
    "min_vol_ratio": 0.8,
    "min_ema_spread_pct": 0.05,
    "min_atr_pct": 0.08,
    # Risk management
    "sl_atr_mult": 1.0,
    "tp1_atr_mult": 1.5,
    "tp2_atr_mult": 2.5,
    "risk_pct": 0.5,                 # % of account per trade
}

REFRESH_SECONDS = 15                 # polling interval
TIMEFRAME = "1m"                     # "1m" or "5m"


# ══════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════
def fetch_klines(symbol: str, interval: str = "1m", limit: int = 150) -> pd.DataFrame:
    """Fetch candlestick data from MEXC public API."""
    url = f"{MEXC_REST}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore"
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df.reset_index(drop=True)


def fetch_ticker(symbol: str) -> dict:
    """Fetch 24hr ticker."""
    url = f"{MEXC_REST}/ticker/24hr"
    r = requests.get(url, params={"symbol": symbol}, timeout=5)
    r.raise_for_status()
    return r.json()


# ══════════════════════════════════════════
#  INDICATORS
# ══════════════════════════════════════════
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).cumsum() / df["volume"].cumsum()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def vol_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
    avg_vol = df["volume"].rolling(period).mean().shift(1)
    return df["volume"] / avg_vol.replace(0, np.nan)


# ══════════════════════════════════════════
#  STRATEGY ENGINE
# ══════════════════════════════════════════
def compute_signal(df: pd.DataFrame) -> dict:
    """
    Core strategy logic.
    Returns a dict with: type, strength, entry, sl, tp1, tp2, indicators
    """
    if len(df) < 30:
        return {"type": "WAIT", "reason": "Insufficient data", "strength": 0}

    cfg = STRATEGY

    # ── Compute indicators ──────────────────
    df = df.copy()
    df["ema9"]     = ema(df["close"], cfg["ema_fast"])
    df["ema21"]    = ema(df["close"], cfg["ema_slow"])
    df["rsi"]      = rsi(df["close"], cfg["rsi_period"])
    df["vwap"]     = vwap(df)
    df["atr"]      = atr(df, cfg["atr_period"])
    df["vol_r"]    = vol_ratio(df, cfg["vol_avg_period"])

    # Current row (latest candle)
    cur = df.iloc[-1]
    prev = df.iloc[-2]

    price    = cur["close"]
    e9       = cur["ema9"]
    e21      = cur["ema21"]
    rsi_val  = cur["rsi"]
    vwap_val = cur["vwap"]
    atr_val  = cur["atr"]
    vr       = cur["vol_r"]
    ema_spread_pct = abs(e9 - e21) / e21 * 100

    # ── Filters: No-Trade Conditions ────────
    no_trades = []
    if rsi_val > cfg["rsi_overbought"]:
        no_trades.append(f"RSI overbought ({rsi_val:.1f})")
    if rsi_val < cfg["rsi_oversold"]:
        no_trades.append(f"RSI oversold ({rsi_val:.1f})")
    if pd.notna(vr) and vr < cfg["min_vol_ratio"]:
        no_trades.append(f"Low volume ({vr:.2f}x avg)")
    if ema_spread_pct < cfg["min_ema_spread_pct"]:
        no_trades.append("EMA too close — choppy/sideways")
    if atr_val / price * 100 < cfg["min_atr_pct"]:
        no_trades.append("ATR too low — no scalp range")

    # ── Score LONG & SHORT ──────────────────
    long_score = 0
    long_reasons = []
    if price > vwap_val:
        long_score += 25; long_reasons.append("Price > VWAP")
    if e9 > e21:
        long_score += 25; long_reasons.append("EMA9 > EMA21 (uptrend)")
    if cfg["rsi_long_min"] <= rsi_val <= cfg["rsi_long_max"]:
        long_score += 20; long_reasons.append(f"RSI {rsi_val:.1f} in long zone")
    if pd.notna(vr) and vr > cfg["vol_ratio_threshold"]:
        long_score += 20; long_reasons.append(f"Volume spike {vr:.2f}x")
    if price > e9 and prev["close"] <= prev["ema9"]:
        long_score += 10; long_reasons.append("Price crossed above EMA9")

    short_score = 0
    short_reasons = []
    if price < vwap_val:
        short_score += 25; short_reasons.append("Price < VWAP")
    if e9 < e21:
        short_score += 25; short_reasons.append("EMA9 < EMA21 (downtrend)")
    if cfg["rsi_short_min"] <= rsi_val <= cfg["rsi_short_max"]:
        short_score += 20; short_reasons.append(f"RSI {rsi_val:.1f} in short zone")
    if pd.notna(vr) and vr > cfg["vol_ratio_threshold"]:
        short_score += 20; short_reasons.append(f"Volume spike {vr:.2f}x")
    if price < e9 and prev["close"] >= prev["ema9"]:
        short_score += 10; short_reasons.append("Price crossed below EMA9")

    # ── Determine Signal ────────────────────
    if no_trades:
        sig_type   = "NO-TRADE"
        strength   = 0
        reasons    = no_trades
    elif long_score >= cfg["min_signal_strength"] and long_score > short_score:
        sig_type   = "LONG"
        strength   = long_score
        reasons    = long_reasons
    elif short_score >= cfg["min_signal_strength"] and short_score > long_score:
        sig_type   = "SHORT"
        strength   = short_score
        reasons    = short_reasons
    elif max(long_score, short_score) >= 50:
        sig_type   = "WATCH"
        strength   = max(long_score, short_score)
        reasons    = ["Setup developing — wait for confirmation"]
    else:
        sig_type   = "WAIT"
        strength   = 0
        reasons    = ["No clear setup — stay flat"]

    # ── Risk Levels ─────────────────────────
    entry = price
    if sig_type == "LONG":
        sl  = entry - atr_val * cfg["sl_atr_mult"]
        tp1 = entry + atr_val * cfg["tp1_atr_mult"]
        tp2 = entry + atr_val * cfg["tp2_atr_mult"]
    elif sig_type == "SHORT":
        sl  = entry + atr_val * cfg["sl_atr_mult"]
        tp1 = entry - atr_val * cfg["tp1_atr_mult"]
        tp2 = entry - atr_val * cfg["tp2_atr_mult"]
    else:
        sl = tp1 = tp2 = 0

    rr = f"1:{cfg['tp1_atr_mult']}" if atr_val > 0 else "—"

    return {
        "type": sig_type,
        "strength": strength,
        "reasons": reasons,
        "no_trades": no_trades,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": rr,
        "indicators": {
            "ema9": e9,
            "ema21": e21,
            "rsi": rsi_val,
            "vwap": vwap_val,
            "atr": atr_val,
            "vol_ratio": vr,
            "ema_spread_pct": ema_spread_pct,
            "trend": "BULL" if e9 > e21 else "BEAR",
        },
    }


# ══════════════════════════════════════════
#  DISPLAY
# ══════════════════════════════════════════
def color_signal(sig_type: str) -> str:
    colors = {
        "LONG":     Fore.GREEN,
        "SHORT":    Fore.RED,
        "NO-TRADE": Fore.RED,
        "WATCH":    Fore.YELLOW,
        "WAIT":     Fore.YELLOW,
    }
    return colors.get(sig_type, Fore.WHITE)


def print_signal(symbol: str, sig: dict, ticker: dict):
    os.system("clear" if os.name != "nt" else "cls")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    price = float(ticker.get("lastPrice", sig["entry"] or 0))
    chg   = float(ticker.get("priceChangePercent", 0))
    ind   = sig["indicators"]

    print(f"{Fore.CYAN}{'═'*60}")
    print(f"  MEXC SCALPER — {Fore.WHITE}{symbol}{Fore.CYAN}  |  {now}")
    print(f"{'═'*60}{Style.RESET_ALL}")

    chg_color = Fore.GREEN if chg >= 0 else Fore.RED
    print(f"  Price : {Fore.WHITE}{price:.6f}{Style.RESET_ALL}  {chg_color}({chg:+.2f}%){Style.RESET_ALL}")
    print(f"  EMA9  : {Fore.CYAN}{ind['ema9']:.6f}{Style.RESET_ALL}  |  "
          f"EMA21: {Fore.MAGENTA}{ind['ema21']:.6f}{Style.RESET_ALL}")
    print(f"  RSI   : {Fore.WHITE}{ind['rsi']:.2f}{Style.RESET_ALL}  |  "
          f"VWAP : {Fore.YELLOW}{ind['vwap']:.6f}{Style.RESET_ALL}")
    print(f"  ATR   : {ind['atr']:.6f}  |  VolRatio: {ind['vol_ratio']:.2f}x  |  "
          f"Trend: {'↑ BULL' if ind['trend']=='BULL' else '↓ BEAR'}")

    print(f"\n{Fore.CYAN}{'─'*60}{Style.RESET_ALL}")
    sig_color = color_signal(sig["type"])
    print(f"  SIGNAL: {sig_color}{sig['type']}{Style.RESET_ALL}  "
          f"(Strength: {sig['strength']}%)")
    print(f"  Reasons: {', '.join(sig['reasons'][:3])}")

    if sig["type"] in ("LONG", "SHORT"):
        print(f"\n  Entry  : {sig['entry']:.6f}")
        print(f"  SL     : {Fore.RED}{sig['sl']:.6f}{Style.RESET_ALL}")
        print(f"  TP1    : {Fore.GREEN}{sig['tp1']:.6f}{Style.RESET_ALL}")
        print(f"  TP2    : {Fore.GREEN}{sig['tp2']:.6f}{Style.RESET_ALL}")
        print(f"  R:R    : {sig['rr']}")

    if sig["type"] == "NO-TRADE":
        print(f"\n  {Fore.YELLOW}⚠ FILTERS TRIGGERED — DO NOT TRADE{Style.RESET_ALL}")
        for r in sig["no_trades"]:
            print(f"    • {r}")

    # ── When NOT to trade (always displayed) ─
    print(f"\n{Fore.CYAN}{'─'*60}{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}DO NOT TRADE WHEN:{Style.RESET_ALL}")
    print(f"    • RSI > 75 (overbought) or RSI < 25 (oversold)")
    print(f"    • Volume ratio < 0.8x avg (fake signal risk)")
    print(f"    • EMA9 / EMA21 within 0.05% (choppy market)")
    print(f"    • ATR < 0.08% of price (no scalp range)")
    print(f"    • Major news within 15min (e.g. CPI, FOMC)")
    print(f"    • Market is in a weekend/low-liquidity session")
    print(f"\n  {Fore.CYAN}Next refresh in {REFRESH_SECONDS}s  |  Ctrl+C to stop{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═'*60}{Style.RESET_ALL}")


# ══════════════════════════════════════════
#  PSEUDO-CODE (printed on first run)
# ══════════════════════════════════════════
PSEUDOCODE = """
╔══════════════════════════════════════════════════════════════╗
║          SCALPING STRATEGY — PSEUDO-CODE                     ║
╚══════════════════════════════════════════════════════════════╝

EVERY CANDLE CLOSE (1m or 5m):
  1. Fetch last 150 candles from MEXC
  2. Compute: EMA9, EMA21, RSI(14), VWAP, ATR(14), VolRatio(20)

  FILTER CHECK (if ANY true → NO-TRADE):
    if RSI > 75 or RSI < 25 → skip
    if VolRatio < 0.8 → skip
    if |EMA9 - EMA21| / EMA21 < 0.05% → skip (choppy)
    if ATR / Price < 0.08% → skip (no range)

  LONG SETUP (score each condition, max 100):
    +25 → Price > VWAP
    +25 → EMA9 > EMA21
    +20 → 45 ≤ RSI ≤ 65
    +20 → VolRatio > 1.5
    +10 → Price crosses above EMA9 (prev close ≤ prev EMA9)
    if total ≥ 70 AND long > short → SIGNAL = LONG

  SHORT SETUP:
    +25 → Price < VWAP
    +25 → EMA9 < EMA21
    +20 → 35 ≤ RSI ≤ 55
    +20 → VolRatio > 1.5
    +10 → Price crosses below EMA9
    if total ≥ 70 AND short > long → SIGNAL = SHORT

  RISK LEVELS:
    entry   = current_price
    stop    = entry ∓ 1.0 × ATR
    target1 = entry ± 1.5 × ATR   (R:R = 1:1.5)
    target2 = entry ± 2.5 × ATR   (R:R = 1:2.5)
    position_size = (account × 0.5%) / ATR

  EXIT RULES:
    → Hard exit: price hits SL or TP
    → Time exit: after 5 candles if no TP hit
    → Momentum exit: RSI crosses 70 (long) or 30 (short)
    → EMA exit: EMA9 crosses back through EMA21
"""


# ══════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════
def main():
    print(PSEUDOCODE)
    time.sleep(2)

    # Run for the first symbol in watchlist; extend with threading for multi-pair
    symbol = WATCHLIST[0]

    print(f"{Fore.CYAN}Starting MEXC Scalper for {symbol} ({TIMEFRAME})...{Style.RESET_ALL}")

    while True:
        try:
            df     = fetch_klines(symbol, TIMEFRAME, 150)
            ticker = fetch_ticker(symbol)
            sig    = compute_signal(df)
            print_signal(symbol, sig, ticker)

        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}Network error: {e}{Style.RESET_ALL}")
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Stopped.{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")

        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
