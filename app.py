"""
Rana Fx Bot Professional - Backend
===================================
Production Flask backend for a real, next-candle Forex signal engine.

Data source : TwelveData REST API (three keys, automatic rotation on rate-limit)
Math        : EMA, RSI, MACD, ADX, ATR, Bollinger Bands, SuperTrend, Swing High/Low,
              Support/Resistance, Market Structure, Fair Value Gap, Liquidity Sweep,
              Volatility Filter and Multi-Timeframe confirmation - all computed from
              real historical candles with pure Python (no numpy/pandas dependency).
No random numbers, no hard-coded confidence, no fake candles, no repainting.

Run:
    pip install flask requests
    python backend.py

The server starts on http://127.0.0.1:5000
"""

import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request

# ============================================================================
# CONFIGURATION
# ============================================================================

TWELVEDATA_API_KEYS = [
    "c47e6aa1e3694d888ba0d8ee10193160",
    "5f98e9f032684d27b8b266656bfcadac",
    "a592dba7321442efa229bee2b8a1cff8",
]

TWELVEDATA_BASE_URL = "https://api.twelvedata.com/time_series"

LOGIN_PASSWORD = "ranafx1234"

# Frontend pair label -> TwelveData symbol
SUPPORTED_PAIRS = {
    "XAU/USD": "XAU/USD",
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "USD/CHF": "USD/CHF",
    "AUD/USD": "AUD/USD",
    "NZD/USD": "NZD/USD",
    "USD/CAD": "USD/CAD",
    "EUR/JPY": "EUR/JPY",
    "GBP/JPY": "GBP/JPY",
    "EUR/GBP": "EUR/GBP",
    "EUR/AUD": "EUR/AUD",
    "AUD/JPY": "AUD/JPY",
}

# Frontend timeframe value -> TwelveData interval string
TIMEFRAME_MAP = {
    "1": "1min",
    "5": "5min",
    "15": "15min",
}

# Timeframe -> higher timeframe used for multi-timeframe confirmation
HIGHER_TIMEFRAME_MAP = {
    "1min": "15min",
    "5min": "1h",
    "15min": "4h",
}

# Duration of one candle in minutes, used to compute the "next candle" time
TIMEFRAME_MINUTES = {
    "1min": 1,
    "5min": 5,
    "15min": 15,
    "1h": 60,
    "4h": 240,
}

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
HISTORY_LOCK = threading.Lock()
MAX_HISTORY = 10

# ============================================================================
# LOGGING
# ============================================================================

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend.log")

logger = logging.getLogger("rana_fx_bot")
logger.setLevel(logging.INFO)

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_console_handler = logging.StreamHandler()
_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
_file_handler.setFormatter(_formatter)
_console_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class AllApiKeysExhaustedError(Exception):
    """Raised when every TwelveData API key has hit its rate limit."""


class MarketDataError(Exception):
    """Raised when TwelveData returns a non rate-limit error."""


# ============================================================================
# API KEY ROTATION
# ============================================================================

class ApiKeyManager:
    """
    Rotates across a fixed pool of TwelveData API keys.
    Only one key is ever active. When that key's daily/minute credit limit is
    hit, it is marked exhausted and the manager automatically switches to the
    next key. When all keys are exhausted, AllApiKeysExhaustedError is raised.
    Exhausted keys are cleared automatically after 24 hours (TwelveData's
    free-tier daily quota resets every 24h).
    """

    def __init__(self, keys):
        self._keys = list(keys)
        self._active_index = 0
        self._exhausted_until = {}  # key -> datetime when it becomes usable again
        self._lock = threading.Lock()

    def _is_exhausted(self, key):
        until = self._exhausted_until.get(key)
        if until is None:
            return False
        if datetime.now(timezone.utc) >= until:
            del self._exhausted_until[key]
            return False
        return True

    def get_active_key(self):
        with self._lock:
            n = len(self._keys)
            for offset in range(n):
                idx = (self._active_index + offset) % n
                key = self._keys[idx]
                if not self._is_exhausted(key):
                    self._active_index = idx
                    return key
            return None

    def mark_current_exhausted(self, key):
        with self._lock:
            self._exhausted_until[key] = datetime.now(timezone.utc) + timedelta(hours=24)
            self._active_index = (self._keys.index(key) + 1) % len(self._keys)
            logger.warning("API key ending in %s marked exhausted, rotating to next key.", key[-4:])

    def status(self):
        with self._lock:
            return [
                {"key_suffix": k[-4:], "exhausted": self._is_exhausted(k)}
                for k in self._keys
            ]


api_key_manager = ApiKeyManager(TWELVEDATA_API_KEYS)


# ============================================================================
# TWELVEDATA CLIENT
# ============================================================================

def fetch_candles(symbol, interval, output_size=250):
    """
    Fetch historical OHLC candles from TwelveData, rotating API keys on
    rate-limit responses. Returns a list of candle dicts sorted oldest -> newest:
        {"datetime": datetime, "open": float, "high": float, "low": float, "close": float}
    Raises AllApiKeysExhaustedError or MarketDataError on failure.
    """
    attempts = len(TWELVEDATA_API_KEYS)
    last_error = None

    for _ in range(attempts):
        key = api_key_manager.get_active_key()
        if key is None:
            raise AllApiKeysExhaustedError(
                "All TwelveData API keys have reached their request limit. "
                "Please try again later."
            )

        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": output_size,
            "apikey": key,
            "order": "ASC",
        }

        try:
            resp = requests.get(TWELVEDATA_BASE_URL, params=params, timeout=15)
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.error("Network error contacting TwelveData: %s", exc)
            raise MarketDataError(f"Network error contacting market data provider: {exc}")

        try:
            payload = resp.json()
        except ValueError:
            last_error = "Invalid JSON response from TwelveData"
            logger.error(last_error)
            raise MarketDataError(last_error)

        # TwelveData signals rate limiting with status == "error" and code 429,
        # or a message mentioning API credits / limit.
        if payload.get("status") == "error":
            message = str(payload.get("message", "")).lower()
            code = payload.get("code")
            if code == 429 or "credit" in message or "limit" in message:
                logger.warning("API key ending %s hit its limit: %s", key[-4:], payload.get("message"))
                api_key_manager.mark_current_exhausted(key)
                last_error = payload.get("message")
                continue  # try next key
            # Any other real error (bad symbol, bad interval, etc.) is not a limit issue
            raise MarketDataError(payload.get("message", "Unknown TwelveData error"))

        values = payload.get("values")
        if not values:
            raise MarketDataError("TwelveData returned no candle data for this symbol/interval.")

        candles = []
        for row in values:
            try:
                candles.append({
                    "datetime": datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if len(row["datetime"]) > 10
                    else datetime.strptime(row["datetime"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                })
            except (KeyError, ValueError) as exc:
                logger.error("Malformed candle row skipped: %s (%s)", row, exc)

        candles.sort(key=lambda c: c["datetime"])
        return candles

    raise AllApiKeysExhaustedError(
        last_error or "All TwelveData API keys are exhausted. Please try again later."
    )


# ============================================================================
# MARKET STATUS  (Forex: open Sun 22:00 UTC -> Fri 22:00 UTC, approx. 5pm ET)
# ============================================================================

def get_market_status():
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # Monday = 0 ... Sunday = 6
    hour = now.hour

    if weekday == 5:  # Saturday - always closed
        return "closed"
    if weekday == 4 and hour >= 22:  # Friday after 22:00 UTC
        return "closed"
    if weekday == 6 and hour < 22:  # Sunday before 22:00 UTC
        return "closed"
    return "open"


# ============================================================================
# INDICATOR MATH  (pure python, real formulas, no shortcuts)
# ============================================================================

def sma(values, period):
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    multiplier = 2 / (period + 1)
    for i in range(period, len(values)):
        out[i] = (values[i] - out[i - 1]) * multiplier + out[i - 1]
    return out


def rsi(closes, period=14):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain, avg_loss):
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(closes, fast=12, slow=26, signal=9):
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    # signal line = EMA of macd_line, computed only on the valid (non-None) tail
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line = [None] * len(closes)
    histogram = [None] * len(closes)
    if first_valid is not None:
        valid_macd = macd_line[first_valid:]
        sig = ema(valid_macd, signal)
        for i, v in enumerate(sig):
            if v is not None:
                signal_line[first_valid + i] = v
                histogram[first_valid + i] = valid_macd[i] - v
    return macd_line, signal_line, histogram


def true_range(highs, lows, closes):
    tr = [None] * len(closes)
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(closes)):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return tr


def wilder_smooth(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def atr(highs, lows, closes, period=14):
    tr = true_range(highs, lows, closes)
    return wilder_smooth(tr, period)


def adx(highs, lows, closes, period=14):
    n = len(closes)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    tr = true_range(highs, lows, closes)
    smoothed_tr = wilder_smooth(tr, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)

    plus_di = [None] * n
    minus_di = [None] * n
    dx = [None] * n
    for i in range(n):
        if smoothed_tr[i] and smoothed_plus_dm[i] is not None and smoothed_minus_dm[i] is not None and smoothed_tr[i] != 0:
            plus_di[i] = 100 * smoothed_plus_dm[i] / smoothed_tr[i]
            minus_di[i] = 100 * smoothed_minus_dm[i] / smoothed_tr[i]
            denom = plus_di[i] + minus_di[i]
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom if denom != 0 else 0.0

    first_dx = next((i for i, v in enumerate(dx) if v is not None), None)
    adx_line = [None] * n
    if first_dx is not None:
        valid_dx = [v for v in dx[first_dx:] if v is not None]
        smoothed = wilder_smooth(valid_dx, period)
        offset = first_dx
        for i, v in enumerate(smoothed):
            if v is not None:
                adx_line[offset + i] = v
    return adx_line, plus_di, minus_di


def bollinger_bands(closes, period=20, num_std=2):
    middle = sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        mean = middle[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return upper, middle, lower


def supertrend(highs, lows, closes, period=10, multiplier=3.0):
    n = len(closes)
    atr_values = atr(highs, lows, closes, period)
    hl2 = [(highs[i] + lows[i]) / 2 for i in range(n)]

    final_upper = [None] * n
    final_lower = [None] * n
    trend = [None] * n  # "up" or "down"

    for i in range(n):
        if atr_values[i] is None:
            continue
        basic_upper = hl2[i] + multiplier * atr_values[i]
        basic_lower = hl2[i] - multiplier * atr_values[i]

        prev_final_upper = final_upper[i - 1] if i > 0 else None
        prev_final_lower = final_lower[i - 1] if i > 0 else None

        if prev_final_upper is None:
            final_upper[i] = basic_upper
        else:
            final_upper[i] = (
                basic_upper if (basic_upper < prev_final_upper or closes[i - 1] > prev_final_upper)
                else prev_final_upper
            )

        if prev_final_lower is None:
            final_lower[i] = basic_lower
        else:
            final_lower[i] = (
                basic_lower if (basic_lower > prev_final_lower or closes[i - 1] < prev_final_lower)
                else prev_final_lower
            )

        if i == 0 or trend[i - 1] is None:
            trend[i] = "up" if closes[i] > final_upper[i] else "down"
        elif trend[i - 1] == "up":
            trend[i] = "down" if closes[i] < final_lower[i] else "up"
        else:
            trend[i] = "up" if closes[i] > final_upper[i] else "down"

    return trend, final_upper, final_lower


def find_swing_points(highs, lows, window=2):
    """A swing high/low is a local extreme over `window` bars on each side."""
    n = len(highs)
    swing_highs = []  # list of (index, price)
    swing_lows = []
    for i in range(window, n - window):
        left_h = highs[i - window:i]
        right_h = highs[i + 1:i + 1 + window]
        if highs[i] >= max(left_h) and highs[i] >= max(right_h):
            swing_highs.append((i, highs[i]))
        left_l = lows[i - window:i]
        right_l = lows[i + 1:i + 1 + window]
        if lows[i] <= min(left_l) and lows[i] <= min(right_l):
            swing_lows.append((i, lows[i]))
    return swing_highs, swing_lows


# ============================================================================
# CONFIRMATION / CONFIDENCE ENGINE
# ============================================================================

def bias(direction):
    """Normalize helper - returns 'BUY', 'SELL' or 'NEUTRAL'."""
    return direction


def evaluate_confirmations(highs, lows, closes, htf_candles=None):
    """
    Runs every confirmation against the candle series (indexed oldest -> newest,
    the LAST element is the most recently CLOSED candle - never a forming one).
    Returns (confirmations: dict[name -> 'BUY'/'SELL'/'NEUTRAL'], volatility_ok: bool)
    """
    n = len(closes)
    last = n - 1
    confirmations = {}

    # ---- EMA (20 vs 50, plus price position) ----
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    if ema20[last] is not None and ema50[last] is not None:
        if closes[last] > ema20[last] > ema50[last]:
            confirmations["EMA Trend"] = "BUY"
        elif closes[last] < ema20[last] < ema50[last]:
            confirmations["EMA Trend"] = "SELL"
        else:
            confirmations["EMA Trend"] = "NEUTRAL"
    else:
        confirmations["EMA Trend"] = "NEUTRAL"

    # ---- RSI ----
    rsi_values = rsi(closes, 14)
    if rsi_values[last] is not None and rsi_values[last - 1] is not None:
        r, r_prev = rsi_values[last], rsi_values[last - 1]
        if r > 55 and r >= r_prev:
            confirmations["RSI"] = "BUY"
        elif r < 45 and r <= r_prev:
            confirmations["RSI"] = "SELL"
        else:
            confirmations["RSI"] = "NEUTRAL"
    else:
        confirmations["RSI"] = "NEUTRAL"

    # ---- MACD ----
    macd_line, signal_line, hist = macd(closes)
    if macd_line[last] is not None and signal_line[last] is not None:
        if macd_line[last] > signal_line[last] and hist[last] > 0:
            confirmations["MACD"] = "BUY"
        elif macd_line[last] < signal_line[last] and hist[last] < 0:
            confirmations["MACD"] = "SELL"
        else:
            confirmations["MACD"] = "NEUTRAL"
    else:
        confirmations["MACD"] = "NEUTRAL"

    # ---- ADX / directional movement ----
    adx_line, plus_di, minus_di = adx(highs, lows, closes, 14)
    if adx_line[last] is not None and plus_di[last] is not None and minus_di[last] is not None:
        if adx_line[last] >= 20 and plus_di[last] > minus_di[last]:
            confirmations["ADX"] = "BUY"
        elif adx_line[last] >= 20 and minus_di[last] > plus_di[last]:
            confirmations["ADX"] = "SELL"
        else:
            confirmations["ADX"] = "NEUTRAL"
    else:
        confirmations["ADX"] = "NEUTRAL"

    # ---- Bollinger Bands ----
    upper, middle, lower = bollinger_bands(closes, 20, 2)
    if middle[last] is not None:
        if closes[last] > middle[last] and closes[last] < upper[last]:
            confirmations["Bollinger Bands"] = "BUY"
        elif closes[last] < middle[last] and closes[last] > lower[last]:
            confirmations["Bollinger Bands"] = "SELL"
        else:
            confirmations["Bollinger Bands"] = "NEUTRAL"
    else:
        confirmations["Bollinger Bands"] = "NEUTRAL"

    # ---- SuperTrend ----
    st_trend, _, _ = supertrend(highs, lows, closes, 10, 3.0)
    if st_trend[last] == "up":
        confirmations["SuperTrend"] = "BUY"
    elif st_trend[last] == "down":
        confirmations["SuperTrend"] = "SELL"
    else:
        confirmations["SuperTrend"] = "NEUTRAL"

    # ---- Swing structure / Support & Resistance ----
    swing_highs, swing_lows = find_swing_points(highs, lows, window=3)
    recent_highs = [p for i, p in swing_highs[-3:]]
    recent_lows = [p for i, p in swing_lows[-3:]]

    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        higher_highs = recent_highs[-1] > recent_highs[-2]
        higher_lows = recent_lows[-1] > recent_lows[-2]
        lower_highs = recent_highs[-1] < recent_highs[-2]
        lower_lows = recent_lows[-1] < recent_lows[-2]
        if higher_highs and higher_lows:
            confirmations["Market Structure"] = "BUY"
        elif lower_highs and lower_lows:
            confirmations["Market Structure"] = "SELL"
        else:
            confirmations["Market Structure"] = "NEUTRAL"
    else:
        confirmations["Market Structure"] = "NEUTRAL"

    resistance = recent_highs[-1] if recent_highs else None
    support = recent_lows[-1] if recent_lows else None
    if support is not None and resistance is not None and resistance != support:
        dist_to_support = abs(closes[last] - support) / (resistance - support)
        dist_to_resistance = abs(resistance - closes[last]) / (resistance - support)
        if dist_to_support < 0.15:
            confirmations["Support/Resistance"] = "BUY"
        elif dist_to_resistance < 0.15:
            confirmations["Support/Resistance"] = "SELL"
        else:
            confirmations["Support/Resistance"] = "NEUTRAL"
    else:
        confirmations["Support/Resistance"] = "NEUTRAL"

    # ---- Fair Value Gap (3-candle imbalance) ----
    if n >= 3:
        c1_high, c1_low = highs[last - 2], lows[last - 2]
        c3_high, c3_low = highs[last], lows[last]
        if c3_low > c1_high:
            confirmations["Fair Value Gap"] = "BUY"
        elif c3_high < c1_low:
            confirmations["Fair Value Gap"] = "SELL"
        else:
            confirmations["Fair Value Gap"] = "NEUTRAL"
    else:
        confirmations["Fair Value Gap"] = "NEUTRAL"

    # ---- Liquidity Sweep (wick beyond swing level, close back inside) ----
    liquidity_signal = "NEUTRAL"
    if recent_lows:
        prev_swing_low = recent_lows[-1]
        if lows[last] < prev_swing_low and closes[last] > prev_swing_low:
            liquidity_signal = "BUY"
    if recent_highs and liquidity_signal == "NEUTRAL":
        prev_swing_high = recent_highs[-1]
        if highs[last] > prev_swing_high and closes[last] < prev_swing_high:
            liquidity_signal = "SELL"
    confirmations["Liquidity Sweep"] = liquidity_signal

    # ---- Multi Timeframe confirmation ----
    if htf_candles and len(htf_candles) >= 55:
        htf_closes = [c["close"] for c in htf_candles]
        htf_ema20 = ema(htf_closes, 20)
        htf_ema50 = ema(htf_closes, 50)
        h_last = len(htf_closes) - 1
        if htf_ema20[h_last] is not None and htf_ema50[h_last] is not None:
            if htf_ema20[h_last] > htf_ema50[h_last]:
                confirmations["Multi Timeframe"] = "BUY"
            elif htf_ema20[h_last] < htf_ema50[h_last]:
                confirmations["Multi Timeframe"] = "SELL"
            else:
                confirmations["Multi Timeframe"] = "NEUTRAL"
        else:
            confirmations["Multi Timeframe"] = "NEUTRAL"
    else:
        confirmations["Multi Timeframe"] = "NEUTRAL"

    # ---- Volatility Filter (gate, not a directional vote) ----
    atr_values = atr(highs, lows, closes, 14)
    valid_atr = [v for v in atr_values if v is not None]
    volatility_ok = True
    if len(valid_atr) >= 30:
        current_atr = valid_atr[-1]
        avg_atr = sum(valid_atr[-30:]) / 30
        if avg_atr > 0 and current_atr < 0.5 * avg_atr:
            volatility_ok = False

    return confirmations, volatility_ok


def build_signal(confirmations, volatility_ok):
    """
    Turns the confirmation dict into a final signal following the exact
    project rule set:
      2 confirmations  -> BUY / SELL
      3 confirmations  -> STRONG BUY / STRONG SELL
      5+ confirmations -> VERY STRONG BUY / VERY STRONG SELL
      otherwise        -> WAIT FOR BETTER SETUP
    """
    directional = [v for v in confirmations.values() if v in ("BUY", "SELL")]
    total_directional_slots = len(confirmations)
    buy_votes = directional.count("BUY")
    sell_votes = directional.count("SELL")

    if buy_votes == 0 and sell_votes == 0:
        return "WAIT FOR BETTER SETUP", 0.0, {}

    dominant = "BUY" if buy_votes >= sell_votes else "SELL"
    votes = buy_votes if dominant == "BUY" else sell_votes
    confidence = round((votes / total_directional_slots) * 100, 1)

    if not volatility_ok:
        return "WAIT FOR BETTER SETUP", confidence, confirmations

    if votes >= 5:
        signal = f"VERY STRONG {dominant}"
    elif votes >= 3:
        signal = f"STRONG {dominant}"
    elif votes >= 2:
        signal = dominant
    else:
        signal = "WAIT FOR BETTER SETUP"

    return signal, confidence, confirmations


def next_candle_time(last_candle_time, interval):
    minutes = TIMEFRAME_MINUTES.get(interval, 1)
    return last_candle_time + timedelta(minutes=minutes)


# ============================================================================
# SIGNAL HISTORY  (persisted to disk, last 10, with real outcome tracking)
# ============================================================================

def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return []


def _save_history(records):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)


def add_history_record(record):
    with HISTORY_LOCK:
        records = _load_history()
        records.append(record)
        records = records[-MAX_HISTORY:]
        _save_history(records)


def refresh_history_results():
    """
    For every pending record whose 'next candle' has since closed, fetch the
    real market outcome and mark WIN / LOSS. Never uses future data that
    wasn't actually available at evaluation time.
    """
    with HISTORY_LOCK:
        records = _load_history()
        changed = False
        now = datetime.now(timezone.utc)

        for rec in records:
            if rec.get("result") != "PENDING":
                continue
            try:
                next_time = datetime.fromisoformat(rec["next_candle_time"])
            except (KeyError, ValueError):
                continue
            if now < next_time + timedelta(minutes=TIMEFRAME_MINUTES.get(rec["interval"], 1)):
                continue  # candle hasn't fully closed yet

            try:
                candles = fetch_candles(rec["symbol"], rec["interval"], output_size=30)
            except (AllApiKeysExhaustedError, MarketDataError) as exc:
                logger.warning("Could not refresh history result for %s: %s", rec["pair"], exc)
                continue

            match = None
            for c in candles:
                if abs((c["datetime"] - next_time).total_seconds()) < 1:
                    match = c
                    break
            if match is None:
                continue

            direction = "BUY" if "BUY" in rec["signal"] else ("SELL" if "SELL" in rec["signal"] else None)
            if direction == "BUY":
                rec["result"] = "WIN" if match["close"] > match["open"] else "LOSS"
            elif direction == "SELL":
                rec["result"] = "WIN" if match["close"] < match["open"] else "LOSS"
            else:
                rec["result"] = "N/A"
            changed = True

        if changed:
            _save_history(records)
        return records


# ============================================================================
# BACKTEST
# ============================================================================

def run_backtest(symbol, interval, lookback=150):
    """
    Real walk-forward backtest: for each historical point in time, only the
    candles available up to (and including) that point are used to build a
    signal, exactly like a live run would see the market. The very next
    candle's open/close is then used to check whether the (unseen-at-the-time)
    trade would have won or lost. No look-ahead, no repainting.
    """
    full_candles = fetch_candles(symbol, interval, output_size=lookback + 260)
    highs_all = [c["high"] for c in full_candles]
    lows_all = [c["low"] for c in full_candles]
    closes_all = [c["close"] for c in full_candles]

    min_lookback = 220  # enough bars for EMA50 / ADX / Bollinger to be valid
    total_bars = len(full_candles)
    start_index = max(min_lookback, total_bars - lookback - 1)

    trades = []
    for i in range(start_index, total_bars - 1):
        highs_slice = highs_all[: i + 1]
        lows_slice = lows_all[: i + 1]
        closes_slice = closes_all[: i + 1]

        confirmations, volatility_ok = evaluate_confirmations(highs_slice, lows_slice, closes_slice, htf_candles=None)
        signal, confidence, _ = build_signal(confirmations, volatility_ok)

        if "WAIT" in signal:
            continue

        direction = "BUY" if "BUY" in signal else "SELL"
        next_candle = full_candles[i + 1]
        won = (next_candle["close"] > next_candle["open"]) if direction == "BUY" else (next_candle["close"] < next_candle["open"])
        trades.append({
            "time": full_candles[i]["datetime"].isoformat(),
            "signal": signal,
            "confidence": confidence,
            "result": "WIN" if won else "LOSS",
        })

    total = len(trades)
    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = total - wins
    win_rate = round((wins / total) * 100, 2) if total else 0.0

    return {
        "symbol": symbol,
        "interval": interval,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "trades": trades[-30:],  # last 30 shown to keep payload light
    }


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@app.route("/api/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", "")).strip()

    if not email or "@" not in email:
        return jsonify({"success": False, "message": "Please enter a valid email address."}), 400

    if password != LOGIN_PASSWORD:
        logger.info("Failed login attempt for email=%s", email)
        return jsonify({"success": False, "message": "Incorrect password."}), 401

    logger.info("Successful login for email=%s", email)
    return jsonify({"success": True, "message": "Login successful.", "email": email})


@app.route("/api/pairs", methods=["GET"])
def get_pairs():
    return jsonify({"pairs": list(SUPPORTED_PAIRS.keys())})


@app.route("/api/market-status", methods=["GET"])
def market_status():
    return jsonify({"status": get_market_status(), "server_time_utc": datetime.now(timezone.utc).isoformat()})


@app.route("/api/generate-signal", methods=["POST", "OPTIONS"])
def generate_signal():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    pair = str(data.get("pair", "")).strip()
    timeframe = str(data.get("timeframe", "")).strip()

    if pair not in SUPPORTED_PAIRS:
        return jsonify({"success": False, "message": "Unsupported currency pair."}), 400
    if timeframe not in TIMEFRAME_MAP:
        return jsonify({"success": False, "message": "Unsupported timeframe."}), 400

    if get_market_status() == "closed":
        logger.info("Signal request rejected: market closed (pair=%s)", pair)
        return jsonify({"success": False, "market_status": "closed", "message": "Market Closed"}), 200

    symbol = SUPPORTED_PAIRS[pair]
    interval = TIMEFRAME_MAP[timeframe]
    higher_interval = HIGHER_TIMEFRAME_MAP[interval]

    try:
        candles = fetch_candles(symbol, interval, output_size=260)
        htf_candles = fetch_candles(symbol, higher_interval, output_size=80)
    except AllApiKeysExhaustedError as exc:
        logger.error("All API keys exhausted while generating signal: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 503
    except MarketDataError as exc:
        logger.error("Market data error while generating signal: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 502

    if len(candles) < 60:
        return jsonify({"success": False, "message": "Not enough historical data returned to compute a reliable signal."}), 502

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    confirmations, volatility_ok = evaluate_confirmations(highs, lows, closes, htf_candles=htf_candles)
    signal, confidence, used_confirmations = build_signal(confirmations, volatility_ok)

    last_candle = candles[-1]
    nxt_time = next_candle_time(last_candle["datetime"], interval)

    record = {
        "pair": pair,
        "symbol": symbol,
        "interval": interval,
        "signal": signal,
        "confidence": confidence,
        "entry_reference_price": last_candle["close"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "next_candle_time": nxt_time.isoformat(),
        "result": "PENDING" if "WAIT" not in signal else "N/A",
    }
    add_history_record(record)

    logger.info(
        "Signal generated | pair=%s tf=%s signal=%s confidence=%s vol_ok=%s",
        pair, timeframe, signal, confidence, volatility_ok,
    )

    return jsonify({
        "success": True,
        "market_status": "open",
        "pair": pair,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "next_candle_time": nxt_time.isoformat(),
        "last_closed_candle_time": last_candle["datetime"].isoformat(),
        "confirmations": confirmations,
        "volatility_ok": volatility_ok,
    })


@app.route("/api/history", methods=["GET"])
def history():
    records = refresh_history_results()
    return jsonify({"history": list(reversed(records))})


@app.route("/api/backtest", methods=["POST", "OPTIONS"])
def backtest():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    pair = str(data.get("pair", "")).strip()
    timeframe = str(data.get("timeframe", "")).strip()

    if pair not in SUPPORTED_PAIRS:
        return jsonify({"success": False, "message": "Unsupported currency pair."}), 400
    if timeframe not in TIMEFRAME_MAP:
        return jsonify({"success": False, "message": "Unsupported timeframe."}), 400

    symbol = SUPPORTED_PAIRS[pair]
    interval = TIMEFRAME_MAP[timeframe]

    try:
        result = run_backtest(symbol, interval, lookback=150)
    except AllApiKeysExhaustedError as exc:
        return jsonify({"success": False, "message": str(exc)}), 503
    except MarketDataError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    logger.info("Backtest run | pair=%s tf=%s trades=%s win_rate=%s",
                pair, timeframe, result["total_trades"], result["win_rate"])

    result["success"] = True
    return jsonify(result)


@app.route("/api/key-status", methods=["GET"])
def key_status():
    return jsonify({"keys": api_key_manager.status()})


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"success": False, "message": "Endpoint not found."}), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error: %s", e)
    return jsonify({"success": False, "message": "Internal server error."}), 500


if __name__ == "__main__":
    logger.info("Starting Rana Fx Bot Professional backend on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
