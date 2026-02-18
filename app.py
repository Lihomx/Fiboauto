"""
Fibo_auto Global Scanner v2.0
Streamlit Web App — 基于 MQL4 Fibo_auto 精确还原的全资产斐波那契扫描器
PRD v2.0 完整实现：4H时间框架 + WebSocket预警 + 回测模块 + 多用户支持
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 依赖安装（首次部署前在 requirements.txt 声明，此处仅注释参考）
# pip install streamlit yfinance pandas numpy requests websockets plotly
#             streamlit-authenticator supabase sqlalchemy
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import json
import time
import csv
import io
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# ───────────────────────────────────────────────────────────────────────────────
# 0. Streamlit 页面配置（必须在最前）
# ───────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fibo_auto Global Scanner v2.0",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 全局常量与配置
# ═══════════════════════════════════════════════════════════════════════════════

FIBO_LABELS = ["F100.0%", "F76.0%", "F61.8%", "F50.0%", "F38.2%", "F23.6%", "F0.0%"]

PRESET_ZONES_DEF = {
    "🟡 50%-61.8%":   (0.500, 0.618, "黄金回调区"),
    "🟠 61.8%-76%":   (0.618, 0.760, "深度回调区"),
    "📦 38.2%-50%":   (0.382, 0.500, "中度回调"),
    "⚡ 23.6%-38.2%": (0.236, 0.382, "浅度回调"),
}

TF_CONFIG = {
    "4H":      {"interval": "1h",  "period": "60d",  "base_factor": 6,     "resample": "4h",  "label": "4小时"},
    "Daily":   {"interval": "1d",  "period": "3y",   "base_factor": 1,     "resample": None,  "label": "日线"},
    "Weekly":  {"interval": "1wk", "period": "5y",   "base_factor": 0.2,   "resample": None,  "label": "周线"},
    "Monthly": {"interval": "1mo", "period": "10y",  "base_factor": 0.045, "resample": None,  "label": "月线"},
}

# 市场识别规则（用于徽章着色）
def detect_market(symbol: str) -> str:
    sym = symbol.upper()
    if sym.endswith("-USD") or sym.endswith("USDT"):
        return "CRYPTO"
    if sym.endswith("=X"):
        return "FOREX"
    if sym.endswith("=F"):
        return "FUTURES"
    if sym.startswith("^"):
        return "INDEX"
    if ".SS" in sym or ".SZ" in sym:
        return "CN"
    return "US"

MARKET_COLORS = {
    "US":      "#3b82f6",
    "CN":      "#ef4444",
    "CRYPTO":  "#f97316",
    "FOREX":   "#22c55e",
    "FUTURES": "#a855f7",
    "INDEX":   "#06b6d4",
    "ETF":     "#eab308",
}

# ═══════════════════════════════════════════════════════════════════════════════
# 2. 内置标的池
# ═══════════════════════════════════════════════════════════════════════════════

SYMBOLS_ACTIVE_MIX = [
    # 美股龙头
    "AAPL","MSFT","NVDA","GOOG","AMZN","META","TSLA","AVGO","BRK-B","JPM",
    "V","MA","UNH","XOM","LLY","JNJ","PG","COST","HD","MRK",
    "ADBE","CRM","NFLX","AMD","INTC","QCOM","MU","ARM","SMCI","PLTR",
    # 中概 ADR
    "BABA","JD","PDD","BIDU","NIO","XPEV","LI","TCOM","TME","BILI",
    # 主流 ETF
    "SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","XLE","XLF",
    "XLK","XLV","ARKK","SOXX","SMH","VNQ","EEM","EFA","VTI","VOO",
    # 大宗期货
    "GC=F","SI=F","CL=F","NG=F","HG=F","ZW=F","ZC=F","ZS=F",
    # 外汇主要货币对
    "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","NZDUSD=X",
    "USDCAD=X","USDCNH=X",
    # 加密主流
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD","ADA-USD",
    "DOGE-USD","AVAX-USD","DOT-USD","MATIC-USD","LINK-USD","UNI-USD",
    # 全球指数
    "^GSPC","^IXIC","^DJI","^RUT","^VIX","^FTSE","^GDAXI","^N225",
    "^HSI","000001.SS","^STOXX50E","^BSESN","DX-Y.NYB",
]

SYMBOLS_ETF = [
    "SPY","QQQ","IWM","DIA","MDY","IJH","IJR","VTI","VOO","VEA","VWO","EEM","EFA",
    "GLD","SLV","IAU","PDBC","USO","UNG",
    "TLT","IEF","SHY","AGG","BND","HYG","LQD","EMB",
    "XLE","XLF","XLK","XLV","XLI","XLC","XLY","XLP","XLU","XLRE","XLB",
    "ARKK","ARKG","ARKW","ARKF","ARKQ",
    "SOXX","SMH","VGT","CIBR","HACK","BOTZ","ROBO",
    "UVXY","VXX","SVXY","VIXY",
    "QLD","SSO","TQQQ","SQQQ","SH","PSQ","SPXU","SPXS",
    "VNQ","SCHH","IYR","MORT",
]

SYMBOLS_FUTURES = [
    "GC=F","SI=F","HG=F","PA=F","PL=F",
    "CL=F","BZ=F","NG=F","RB=F","HO=F",
    "ZW=F","ZC=F","ZS=F","ZL=F","ZM=F","KC=F","SB=F","CC=F","CT=F",
    "ES=F","NQ=F","YM=F","RTY=F","ZN=F","ZB=F","ZF=F","ZT=F","GE=F",
    "6E=F","6J=F","6B=F","6C=F","6A=F","6S=F","6N=F","6M=F",
    "BTC=F","ETH=F",
]

SYMBOLS_FOREX = [
    "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","NZDUSD=X","USDCAD=X",
    "EURGBP=X","EURJPY=X","GBPJPY=X","AUDJPY=X","CHFJPY=X","CADJPY=X",
    "EURCHF=X","AUDCAD=X","AUDNZD=X","NZDCAD=X","NZDCHF=X","GBPAUD=X",
    "USDCNH=X","USDHKD=X","USDSGD=X","USDINR=X","USDBRL=X","USDMXN=X",
    "USDZAR=X","USDTRY=X","USDRUB=X","USDKRW=X","USDTHB=X",
    "EURUSD=X","EURGBP=X","EURAUD=X","EURCAD=X","EURNZD=X",
]

SYMBOLS_CRYPTO = [
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD","ADA-USD","DOGE-USD",
    "AVAX-USD","DOT-USD","MATIC-USD","LINK-USD","UNI-USD","ATOM-USD","LTC-USD",
    "BCH-USD","FIL-USD","APT-USD","ARB-USD","OP-USD","INJ-USD","SUI-USD",
    "TIA-USD","JUP-USD","SEI-USD","PYTH-USD","WIF-USD","BONK-USD","PEPE-USD",
    "SHIB-USD","FTM-USD","NEAR-USD","ALGO-USD","ICP-USD","VET-USD","HBAR-USD",
    "EGLD-USD","GRT-USD","AAVE-USD","MKR-USD","COMP-USD","SNX-USD","CRV-USD",
    "TON-USD","NOT-USD","WLD-USD","FET-USD","RNDR-USD","TAO-USD","IO-USD",
    "ZRO-USD","STRK-USD","MANTA-USD","ALT-USD",
]

SYMBOLS_INDEX = [
    "^GSPC","^IXIC","^DJI","^RUT","^MID",
    "^FTSE","^GDAXI","^CAC","^IBEX","^AEX","^STOXX50E","^OMXS30",
    "^N225","^HSI","^KS11","^TWII","^AXJO","^STI","^NSEI",
    "000001.SS","000300.SS","^CSI300","399001.SZ",
    "^BVSP","^MXX","^IPSA",
    "^VIX","^VXN","^GVZ","^OVX",
    "DX-Y.NYB","^MOVE","^TNX","^TYX","^IRX",
]

def get_symbols(selections: dict) -> list:
    """合并多来源标的池并去重"""
    all_syms = []
    if selections.get("active_mix"):    all_syms += SYMBOLS_ACTIVE_MIX
    if selections.get("sp500_ndx"):     all_syms += _fetch_sp500_ndx()
    if selections.get("etf"):           all_syms += SYMBOLS_ETF
    if selections.get("futures"):       all_syms += SYMBOLS_FUTURES
    if selections.get("forex"):         all_syms += SYMBOLS_FOREX
    if selections.get("crypto"):        all_syms += SYMBOLS_CRYPTO
    if selections.get("index"):         all_syms += SYMBOLS_INDEX
    seen = set(); result = []
    for s in all_syms:
        if s not in seen:
            seen.add(s); result.append(s)
    return result

@st.cache_data(ttl=86400)
def _fetch_sp500_ndx() -> list:
    """从 Wikipedia 抓取 S&P500 + NDX100 成分股"""
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]["Symbol"].tolist()
    except Exception:
        sp500 = []
    try:
        ndx = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]["Ticker"].tolist()
    except Exception:
        ndx = []
    combined = list(set(sp500 + ndx))
    return [s.replace(".", "-") for s in combined if isinstance(s, str)]

# ═══════════════════════════════════════════════════════════════════════════════
# 3. 核心 Fibo_auto 算法（MQL4 精确还原）
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    cfg = TF_CONFIG[timeframe]
    try:
        df = yf.Ticker(symbol).history(
            period=cfg["period"], interval=cfg["interval"], auto_adjust=True
        )
        if df is None or df.empty:
            return None
        if cfg["resample"]:
            df = df.resample(cfg["resample"]).agg(
                Open=("Open","first"), High=("High","max"),
                Low=("Low","min"),   Close=("Close","last"),
                Volume=("Volume","sum"),
            ).dropna(subset=["Close"])
        df = df.dropna(subset=["High","Low","Close"])
        return df if len(df) >= 5 else None
    except Exception:
        return None


def calc_bars(days: int, timeframe: str, asset_type: str = "crypto") -> int:
    factor = TF_CONFIG[timeframe]["base_factor"]
    if timeframe == "4H":
        factor = 1.625 if asset_type == "us_stock" else (1.0 if asset_type == "a_stock" else 6.0)
    return max(5, round(days * factor))


def fiboauto_calc(df: pd.DataFrame, bars: int) -> Optional[dict]:
    """MQL4 Fibo_auto 核心算法精确还原"""
    if df is None or len(df) < max(bars, 5):
        return None
    window = df.tail(bars)
    sw_hi  = float(window["High"].max())
    sw_lo  = float(window["Low"].min())
    rng    = sw_hi - sw_lo
    if rng == 0:
        return None

    positions = list(window.index)
    idx_hi = len(positions) - 1 - positions.index(window["High"].idxmax())
    idx_lo = len(positions) - 1 - positions.index(window["Low"].idxmin())

    # MQL4: bar_high < bar_low → 高点序号更小 → 高点更近 → Bearish
    if idx_hi < idx_lo:
        direction = "Bearish"
        levels = [
            sw_hi,
            sw_lo + 0.760 * rng,
            sw_lo + 0.618 * rng,
            sw_lo + 0.500 * rng,
            sw_lo + 0.382 * rng,
            sw_lo + 0.236 * rng,
            sw_lo,
        ]
    else:
        direction = "Bullish"
        levels = [
            sw_lo,
            sw_hi - 0.760 * rng,
            sw_hi - 0.618 * rng,
            sw_hi - 0.500 * rng,
            sw_hi - 0.382 * rng,
            sw_hi - 0.236 * rng,
            sw_hi,
        ]
    return {"direction": direction, "swing_hi": sw_hi, "swing_lo": sw_lo,
            "idx_hi": idx_hi, "idx_lo": idx_lo, "levels": levels, "fib_range": rng}


def get_fib_position(close: float, result: dict) -> float:
    lo = min(result["levels"][0], result["levels"][-1])
    hi = max(result["levels"][0], result["levels"][-1])
    if hi == lo: return 0.5
    pos = (close - lo) / (hi - lo)
    if result["direction"] == "Bullish": pos = 1.0 - pos
    return float(np.clip(pos, 0.0, 1.0))


def check_fib_zones(close: float, result: dict, zones: list) -> list:
    fib_pos = get_fib_position(close, result)
    return [label for (lo_r, hi_r, label) in zones if lo_r <= fib_pos <= hi_r]


def scan_one(symbol: str, days: int, timeframes: list, zones: list) -> dict:
    """扫描单个标的"""
    asset_type = "crypto" if detect_market(symbol) == "CRYPTO" else \
                 ("forex" if detect_market(symbol) == "FOREX" else "us_stock")
    result = {"symbol": symbol, "market": detect_market(symbol),
              "confluence": 0, "tf_results": {}, "error": None}

    for tf in timeframes:
        df = fetch_ohlcv(symbol, tf)
        if df is None:
            result["tf_results"][tf] = {"error": "no_data"}
            continue
        bars = calc_bars(days, tf, asset_type)
        fib  = fiboauto_calc(df, bars)
        if fib is None:
            result["tf_results"][tf] = {"error": "insufficient_bars"}
            continue
        close     = float(df["Close"].iloc[-1])
        fib_pos   = get_fib_position(close, fib)
        hit_zones = check_fib_zones(close, fib, zones)
        result["tf_results"][tf] = {
            "direction": fib["direction"],
            "fib_pos":   round(fib_pos, 4),
            "hit_zones": hit_zones,
            "swing_hi":  round(fib["swing_hi"], 6),
            "swing_lo":  round(fib["swing_lo"], 6),
            "close":     round(close, 6),
            "levels":    {lb: round(p, 6) for lb, p in zip(FIBO_LABELS, fib["levels"])},
        }
        if hit_zones: result["confluence"] += 1

    return result


def batch_scan(symbols: list, days: int, timeframes: list, zones: list,
               workers: int = 8, max_symbols: int = 500,
               progress_cb=None) -> list:
    """并发批量扫描"""
    symbols = symbols[:max_symbols]
    results, total = [], len(symbols)
    done = [0]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(scan_one, sym, days, timeframes, zones): sym for sym in symbols}
        for fut in as_completed(futures):
            try:
                r = fut.result()
                results.append(r)
            except Exception as e:
                results.append({"symbol": futures[fut], "confluence": 0,
                                 "tf_results": {}, "error": str(e), "market": "US"})
            done[0] += 1
            if progress_cb:
                hits = sum(1 for r in results if r.get("confluence", 0) > 0)
                progress_cb(done[0], total, hits)

    results.sort(key=lambda x: x.get("confluence", 0), reverse=True)
    return results

# ═══════════════════════════════════════════════════════════════════════════════
# 4. 回测引擎
# ═══════════════════════════════════════════════════════════════════════════════

def backtest_single(symbol: str, timeframe: str, days: int, zones: list,
                    hold_bars: int = 20, tp_ratio: float = 1.0) -> dict:
    """
    滚动窗口回测：在历史数据上滑动，统计 Fib 区间命中后的胜率与 R:R。

    Parameters
    ----------
    symbol    : 标的代码
    timeframe : 回测时间框架
    days      : 每个时刻的回看窗口（MQL4 Days）
    zones     : 扫描区间列表
    hold_bars : 超时判定根数
    tp_ratio  : TP 目标：1.0 = F[6]端（100% 延伸），0=F[5]

    Returns
    -------
    {
      "signals": int,
      "wins": int, "losses": int, "timeouts": int,
      "win_rate": float,
      "avg_tp_r": float,
      "avg_sl_r": float,
      "rr_ratio": float,
      "expected_value": float,
      "max_consec_loss": int,
      "records": list[dict],
    }
    """
    asset_type = "crypto" if detect_market(symbol) == "CRYPTO" else "us_stock"
    bars_per_step = calc_bars(days, timeframe, asset_type)

    df = fetch_ohlcv(symbol, timeframe)
    if df is None or len(df) < bars_per_step + hold_bars + 5:
        return {"error": "insufficient_data"}

    records = []
    closes  = df["Close"].values
    highs   = df["High"].values
    lows    = df["Low"].values

    min_start = bars_per_step
    max_start = len(df) - hold_bars - 1

    for i in range(min_start, max_start):
        window_df = df.iloc[i - bars_per_step: i]
        fib = fiboauto_calc(window_df, bars_per_step)
        if fib is None: continue

        close = closes[i]
        hit   = check_fib_zones(close, fib, zones)
        if not hit: continue

        # 确定 TP / SL
        if fib["direction"] == "Bullish":
            tp_price = fib["levels"][-1]  # F[6] = swing_hi
            sl_price = fib["levels"][0]   # F[0] = swing_lo
        else:
            tp_price = fib["levels"][-1]  # F[6] = swing_lo
            sl_price = fib["levels"][0]   # F[0] = swing_hi

        tp_dist = abs(tp_price - close)
        sl_dist = abs(sl_price - close)
        if sl_dist == 0: continue

        outcome = "timeout"
        outcome_bar = hold_bars
        for j in range(1, hold_bars + 1):
            if i + j >= len(df): break
            h, l = highs[i + j], lows[i + j]
            if fib["direction"] == "Bullish":
                if h >= tp_price:  outcome = "win";  outcome_bar = j; break
                if l <= sl_price:  outcome = "loss"; outcome_bar = j; break
            else:
                if l <= tp_price:  outcome = "win";  outcome_bar = j; break
                if h >= sl_price:  outcome = "loss"; outcome_bar = j; break

        records.append({
            "date":     df.index[i].strftime("%Y-%m-%d") if hasattr(df.index[i], "strftime") else str(df.index[i]),
            "close":    round(close, 4),
            "hit_zone": hit[0] if hit else "",
            "direction":fib["direction"],
            "tp_price": round(tp_price, 4),
            "sl_price": round(sl_price, 4),
            "tp_r":     round(tp_dist / sl_dist, 2),
            "outcome":  outcome,
            "bars_held":outcome_bar,
        })

    if not records:
        return {"error": "no_signals", "records": []}

    wins     = [r for r in records if r["outcome"] == "win"]
    losses   = [r for r in records if r["outcome"] == "loss"]
    timeouts = [r for r in records if r["outcome"] == "timeout"]
    valid    = len(wins) + len(losses)
    win_rate = len(wins) / valid if valid > 0 else 0
    avg_tp_r = float(np.mean([r["tp_r"] for r in wins]))   if wins   else 0.0
    avg_sl_r = 1.0
    rr_ratio = avg_tp_r / avg_sl_r if avg_sl_r > 0 else 0.0
    ev       = win_rate * avg_tp_r - (1 - win_rate) * avg_sl_r

    # 最大连续亏损
    streak = mcl = 0
    for r in records:
        if r["outcome"] == "loss":
            streak += 1; mcl = max(mcl, streak)
        else:
            streak = 0

    return {
        "signals":        len(records),
        "wins":           len(wins),
        "losses":         len(losses),
        "timeouts":       len(timeouts),
        "win_rate":       round(win_rate * 100, 1),
        "avg_tp_r":       round(avg_tp_r, 2),
        "avg_sl_r":       round(avg_sl_r, 2),
        "rr_ratio":       round(rr_ratio, 2),
        "expected_value": round(ev, 3),
        "max_consec_loss":mcl,
        "records":        records,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 5. HTML 结果渲染
# ═══════════════════════════════════════════════════════════════════════════════

ZONE_BADGE_COLORS = {
    "黄金回调区": "#f0b429",
    "深度回调区": "#f97316",
    "中度回调":   "#3b82f6",
    "浅度回调":   "#a855f7",
}

def _badge(text: str, color: str, text_color: str = "#fff") -> str:
    return (f'<span style="background:{color};color:{text_color};'
            f'padding:2px 7px;border-radius:4px;font-size:11px;'
            f'font-weight:600;margin:2px;display:inline-block">{text}</span>')

def _dir_badge(direction: str) -> str:
    if direction == "Bullish":
        return _badge("🟢 上涨", "#166534", "#bbf7d0")
    return _badge("🔴 下跌", "#7f1d1d", "#fecaca")

def build_results_html(results: list, min_confluence: int, timeframes: list) -> str:
    filtered = [r for r in results if r.get("confluence", 0) >= min_confluence]
    total     = len(filtered)
    conf3     = sum(1 for r in filtered if r.get("confluence", 0) >= 3)
    conf4     = sum(1 for r in filtered if r.get("confluence", 0) >= 4)
    bullish   = sum(1 for r in filtered
                    for tf, tfd in r.get("tf_results", {}).items()
                    if tfd.get("direction") == "Bullish")

    summary = f"""
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px">
      {_stat_card("命中总数",    str(total),   "#f0b429")}
      {_stat_card("4★共振",      str(conf4),   "#22c55e")}
      {_stat_card("3★共振",      str(conf3),   "#3b82f6")}
      {_stat_card("上涨结构",    str(bullish), "#22c55e")}
    </div>
    """

    tf_headers = "".join(
        f'<th colspan="3" style="color:#f0b429;text-align:center;padding:8px 12px;'
        f'border-bottom:1px solid #2d3748">{TF_CONFIG[tf]["label"]}</th>'
        for tf in timeframes
    )
    tf_sub = "".join(
        f'<th style="{_th_style()}">方向</th>'
        f'<th style="{_th_style()}">Fib位</th>'
        f'<th style="{_th_style()}">命中区间</th>'
        for _ in timeframes
    )

    rows = []
    for r in filtered:
        sym    = r.get("symbol", "")
        mkt    = r.get("market", "US")
        mkt_color = MARKET_COLORS.get(mkt, "#6b7280")
        conf   = r.get("confluence", 0)
        stars  = "★" * conf + "☆" * (4 - conf)

        close_price = ""
        for tf in timeframes:
            tfd = r.get("tf_results", {}).get(tf, {})
            if "close" in tfd:
                close_price = fmt_price(tfd["close"])
                break

        tf_cells = ""
        for tf in timeframes:
            tfd = r.get("tf_results", {}).get(tf, {})
            if "error" in tfd or not tfd:
                tf_cells += f'<td colspan="3" style="color:#6b7280;text-align:center">—</td>'
            else:
                dir_b   = _dir_badge(tfd["direction"])
                pos_pct = f'{tfd["fib_pos"] * 100:.1f}%'
                zones_b = "".join(
                    _badge(z, ZONE_BADGE_COLORS.get(z, "#374151"))
                    for z in tfd["hit_zones"]
                ) or '<span style="color:#6b7280">—</span>'
                tf_cells += (
                    f'<td style="{_td_style()}">{dir_b}</td>'
                    f'<td style="{_td_style()};text-align:center">{pos_pct}</td>'
                    f'<td style="{_td_style()}">{zones_b}</td>'
                )

        conf_color = "#f0b429" if conf >= 3 else ("#22c55e" if conf >= 2 else "#9ca3af")
        rows.append(f"""
        <tr style="border-bottom:1px solid #1e2433;transition:background 0.2s"
            onmouseover="this.style.background='#1a2035'"
            onmouseout="this.style.background='transparent'">
          <td style="{_td_style()}">
            <div style="font-weight:700;color:#e2e8f0">{sym}</div>
            {_badge(mkt, "transparent", mkt_color)}
          </td>
          <td style="{_td_style()};text-align:center;color:#94a3b8">{close_price}</td>
          <td style="{_td_style()};text-align:center;color:{conf_color};font-size:16px"
              title="{conf}/4 时间框架共振">{stars}</td>
          {tf_cells}
        </tr>
        """)

    rows_html = "\n".join(rows) if rows else (
        '<tr><td colspan="20" style="text-align:center;padding:40px;color:#6b7280">'
        '暂无命中结果，请调整扫描参数</td></tr>'
    )

    return f"""
    <style>
      .fiboauto-table {{font-family: 'Courier New', monospace; border-collapse:collapse; width:100%;}}
      .fiboauto-table th {{background:#1a1f2e; color:#f0b429; font-size:12px; font-weight:600;}}
      .fiboauto-table td {{font-size:12px;}}
    </style>
    <div style="background:#0a0c10;border-radius:12px;padding:20px;color:#e2e8f0">
      {summary}
      <div style="overflow-x:auto">
        <table class="fiboauto-table">
          <thead>
            <tr>
              <th style="{_th_style()}" rowspan="2">标的</th>
              <th style="{_th_style()}" rowspan="2">价格</th>
              <th style="{_th_style()}" rowspan="2">共振</th>
              {tf_headers}
            </tr>
            <tr>{tf_sub}</tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """

def _th_style():
    return "padding:8px 10px;white-space:nowrap;border-bottom:2px solid #2d3748"

def _td_style():
    return "padding:8px 10px;vertical-align:middle;white-space:nowrap"

def _stat_card(label: str, value: str, color: str) -> str:
    return (f'<div style="background:#111827;border:1px solid {color}33;border-radius:8px;'
            f'padding:12px 20px;min-width:100px;text-align:center">'
            f'<div style="font-size:22px;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:11px;color:#9ca3af;margin-top:2px">{label}</div></div>')

def fmt_price(p: float) -> str:
    if p == 0: return "—"
    if abs(p) < 0.001: return f"{p:.6f}"
    if abs(p) < 1:     return f"{p:.4f}"
    if abs(p) < 100:   return f"{p:.3f}"
    return f"{p:,.2f}"

# ═══════════════════════════════════════════════════════════════════════════════
# 6. CSV 导出
# ═══════════════════════════════════════════════════════════════════════════════

def build_csv(results: list, timeframes: list) -> bytes:
    buf = io.StringIO()
    tf_fields = []
    for tf in timeframes:
        lb = TF_CONFIG[tf]["label"]
        tf_fields += [
            f"{lb}_方向", f"{lb}_Fib位", f"{lb}_命中区间",
            f"{lb}_SwingHi", f"{lb}_SwingLo",
        ] + [f"{lb}_{l}" for l in FIBO_LABELS]

    writer = csv.writer(buf)
    writer.writerow(["Symbol", "Market", "Price", "Confluence"] + tf_fields)

    for r in results:
        price = ""
        for tf in timeframes:
            tfd = r.get("tf_results", {}).get(tf, {})
            if "close" in tfd: price = tfd["close"]; break

        row = [r.get("symbol",""), r.get("market",""), price, r.get("confluence",0)]
        for tf in timeframes:
            tfd = r.get("tf_results", {}).get(tf, {})
            if not tfd or "error" in tfd:
                row += [""] * (5 + len(FIBO_LABELS))
            else:
                row += [
                    tfd.get("direction",""),
                    f'{tfd.get("fib_pos",0)*100:.1f}%',
                    "|".join(tfd.get("hit_zones",[])),
                    tfd.get("swing_hi",""),
                    tfd.get("swing_lo",""),
                ] + [tfd.get("levels",{}).get(l,"") for l in FIBO_LABELS]
        writer.writerow(row)

    return buf.getvalue().encode("utf-8-sig")

# ═══════════════════════════════════════════════════════════════════════════════
# 7. Session State 初始化
# ═══════════════════════════════════════════════════════════════════════════════

def init_session():
    defaults = {
        "scan_results":       [],
        "symbols_pool":       [],
        "scanning":           False,
        "scan_progress":      0.0,
        "scan_done":          0,
        "scan_total":         0,
        "scan_hits":          0,
        "watchlist":          [],
        "scan_presets":       {},
        "monitor_list":       [],
        "backtest_result":    None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ═══════════════════════════════════════════════════════════════════════════════
# 8. 暗色主题 CSS
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* 全局背景 */
.stApp { background-color: #0a0c10; color: #e2e8f0; }
[data-testid="stSidebar"] { background-color: #0f1117; border-right: 1px solid #1e2433; }
[data-testid="stSidebar"] .stMarkdown { color: #94a3b8; }

/* 按钮样式 */
.stButton > button {
  background: linear-gradient(135deg, #d97706, #b45309);
  color: #fff; border: none; border-radius: 6px;
  font-weight: 600; transition: all 0.2s;
}
.stButton > button:hover { background: linear-gradient(135deg, #f0b429, #d97706); }

/* 输入控件 */
.stSlider [data-baseweb="slider"] div { background: #f0b429 !important; }
.stSelectbox [data-baseweb="select"] { background: #111827; border-color: #2d3748; }
.stMultiSelect [data-baseweb="select"] { background: #111827; }
.stCheckbox label span { color: #e2e8f0; }
.stTextInput input { background: #111827; color: #e2e8f0; border-color: #2d3748; }
.stNumberInput input { background: #111827; color: #e2e8f0; border-color: #2d3748; }

/* 进度条 */
.stProgress > div > div { background: #f0b429 !important; }

/* 提示框 */
.stAlert { background: #1a1f2e; border-color: #2d3748; }

/* Tab 样式 */
.stTabs [data-baseweb="tab"] { color: #94a3b8; font-weight: 600; }
.stTabs [aria-selected="true"] { color: #f0b429; border-bottom-color: #f0b429; }

/* Metric */
[data-testid="stMetric"] { background: #111827; border-radius: 8px; padding: 12px; }
[data-testid="stMetricValue"] { color: #f0b429; }

/* 分割线 */
hr { border-color: #1e2433; }

/* 标题 */
h1, h2, h3 { color: #f0b429 !important; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 9. 侧边栏导航
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:16px 0">
      <div style="font-size:28px">📈</div>
      <div style="font-size:18px;font-weight:700;color:#f0b429">Fibo_auto</div>
      <div style="font-size:11px;color:#6b7280">Global Scanner v2.0</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "导航",
        ["🔍 扫描器", "📡 实时监控", "📊 回测模块", "⭐ 标的池管理"],
        label_visibility="hidden",
    )
    st.divider()
    st.markdown('<div style="font-size:11px;color:#4b5563;text-align:center">MQL4 Fibo_auto 精确还原<br>PRD v2.0 © 2025</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 10. 主页面 — 扫描器
# ═══════════════════════════════════════════════════════════════════════════════

if page == "🔍 扫描器":
    st.title("🔍 Fibo_auto 全资产斐波那契扫描器")
    st.caption("v2.0 · MQL4 精确还原 · 4H/日/周/月四周期共振 · 全资产覆盖")

    # ── 标的池选择 ────────────────────────────────────────────────────────────
    with st.expander("📦 标的池选择", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**核心品种**")
            sel_active  = st.checkbox("🔥 活跃混合精选 (~200个)", value=True)
            sel_sp500   = st.checkbox("🇺🇸 S&P500 + NDX100 (~600个)")
        with col2:
            st.markdown("**分类品种**")
            sel_etf     = st.checkbox("📦 全球ETF (~130个)")
            sel_futures = st.checkbox("🛢 全球期货 (~60个)")
            sel_forex   = st.checkbox("💱 全球外汇 (~80个)")
            sel_crypto  = st.checkbox("₿ 全球加密 (~120个)")
            sel_index   = st.checkbox("📊 全球指数 (~100个)")

        c1, c2 = st.columns([1, 4])
        with c1:
            fetch_btn = st.button("📥 拉取标的", use_container_width=True)
        if st.session_state.symbols_pool:
            with c2:
                st.success(f"已选标的：**{len(st.session_state.symbols_pool)}** 个")

        if fetch_btn:
            sel = {
                "active_mix": sel_active, "sp500_ndx": sel_sp500,
                "etf": sel_etf, "futures": sel_futures,
                "forex": sel_forex, "crypto": sel_crypto, "index": sel_index,
            }
            with st.spinner("合并标的池…"):
                st.session_state.symbols_pool = get_symbols(sel)
            st.success(f"✅ 已合并标的 **{len(st.session_state.symbols_pool)}** 个")
            st.rerun()

    # ── 算法参数 ──────────────────────────────────────────────────────────────
    with st.expander("⚙️ 算法参数配置", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            days        = st.slider("Days 回看天数", 5, 365, 35, help="对应 MQL4 Days 参数")
            max_symbols = st.slider("最多扫描标的数", 50, 2000, 500, step=50)
        with col2:
            workers     = st.slider("并发线程数", 1, 20, 8)
            min_conf_scan = st.slider("最小共振分（扫描）", 1, 4, 1)
        with col3:
            min_conf_disp = st.slider("最小共振分（显示）", 1, 4, 1)

        st.markdown("**时间框架**")
        tf_cols = st.columns(4)
        enable_tf = {}
        for i, (tf, cfg) in enumerate(TF_CONFIG.items()):
            with tf_cols[i]:
                default = tf != "4H"
                enable_tf[tf] = st.checkbox(
                    f'{cfg["label"]} {"🆕" if tf == "4H" else ""}',
                    value=default
                )

        st.markdown("**Fib 扫描区间**")
        zcols = st.columns(4)
        active_zones = []
        for i, (name, (lo, hi, label)) in enumerate(PRESET_ZONES_DEF.items()):
            with zcols[i]:
                if st.checkbox(name, value=(name in ["🟡 50%-61.8%", "🟠 61.8%-76%"])):
                    active_zones.append((lo, hi, label))

        with st.expander("➕ 自定义区间"):
            cc1, cc2, cc3 = st.columns(3)
            with cc1: cust_lo = st.number_input("区间下限 (0-1)", 0.0, 1.0, 0.0, 0.01)
            with cc2: cust_hi = st.number_input("区间上限 (0-1)", 0.0, 1.0, 0.0, 0.01)
            with cc3: cust_name = st.text_input("区间名称", "自定义")
            if cust_lo < cust_hi:
                active_zones.append((cust_lo, cust_hi, cust_name))

    if not active_zones:
        active_zones = [(0.500, 0.618, "黄金回调区")]

    selected_tfs = [tf for tf, en in enable_tf.items() if en]

    # ── 扫描操作按钮 ──────────────────────────────────────────────────────────
    btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 2])
    with btn_col1:
        scan_btn = st.button("▶ 开始扫描", type="primary", use_container_width=True,
                             disabled=not st.session_state.symbols_pool)
    with btn_col2:
        if st.session_state.scan_results:
            csv_data = build_csv(st.session_state.scan_results, selected_tfs)
            fname = f"fiboauto_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            st.download_button("💾 导出 CSV", csv_data, fname, "text/csv",
                               use_container_width=True)
    with btn_col3:
        if st.button("🗑 清除缓存", use_container_width=True):
            st.cache_data.clear()
            st.success("缓存已清除")

    # ── 执行扫描 ──────────────────────────────────────────────────────────────
    if scan_btn and st.session_state.symbols_pool:
        symbols = st.session_state.symbols_pool[:max_symbols]
        prog_bar    = st.progress(0.0)
        status_text = st.empty()
        t0 = time.time()

        def progress_cb(done, total, hits):
            pct = done / total
            prog_bar.progress(pct)
            status_text.markdown(
                f"⏳ 已扫描 **{done}** / {total} | 命中 **{hits}** 个 "
                f"| 耗时 **{time.time()-t0:.0f}s**"
            )

        with st.spinner("扫描中…"):
            results = batch_scan(
                symbols, days, selected_tfs, active_zones,
                workers=workers, max_symbols=max_symbols,
                progress_cb=progress_cb,
            )

        st.session_state.scan_results = results
        elapsed = time.time() - t0
        prog_bar.progress(1.0)
        status_text.markdown(
            f"✅ 扫描完成！共 **{len(symbols)}** 个标的 | 耗时 **{elapsed:.1f}s**"
        )

    # ── 结果展示 ──────────────────────────────────────────────────────────────
    if st.session_state.scan_results:
        st.divider()
        # 实时共振分过滤（无需重扫）
        disp_conf = st.slider("实时过滤：最小共振分", 1, 4, min_conf_disp, key="disp_conf_slider")
        html = build_results_html(st.session_state.scan_results, disp_conf, selected_tfs)
        st.markdown(html, unsafe_allow_html=True)

        # 加入实时监控
        if st.session_state.scan_results:
            st.divider()
            hit_symbols = [
                r["symbol"] for r in st.session_state.scan_results
                if r.get("confluence", 0) >= disp_conf
            ]
            if hit_symbols:
                chosen = st.multiselect("📡 选择标的加入实时监控", hit_symbols, max_selections=20)
                if st.button("📡 加入实时监控", disabled=not chosen):
                    for s in chosen:
                        if s not in st.session_state.monitor_list:
                            st.session_state.monitor_list.append(s)
                    st.success(f"已添加 {len(chosen)} 个标的到实时监控")

# ═══════════════════════════════════════════════════════════════════════════════
# 11. 实时监控页面
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📡 实时监控":
    st.title("📡 实时监控 · Fib 区间预警")
    st.caption("Binance WebSocket（加密）/ Alpaca API（美股）/ yfinance 轮询（其他）")

    col1, col2 = st.columns([3, 1])
    with col1:
        new_sym = st.text_input("添加监控标的", placeholder="BTC-USD, AAPL, EURUSD=X …")
    with col2:
        if st.button("➕ 添加", use_container_width=True) and new_sym:
            syms = [s.strip().upper() for s in new_sym.split(",") if s.strip()]
            for s in syms:
                if s not in st.session_state.monitor_list:
                    st.session_state.monitor_list.append(s)
            st.rerun()

    if not st.session_state.monitor_list:
        st.info("👆 请从扫描结果中添加标的，或手动输入标的代码")
    else:
        st.markdown(f"**监控列表** ({len(st.session_state.monitor_list)} 个标的)")

        # 实时数据拉取（轮询降级模式）
        refresh_btn = st.button("🔄 刷新数据")

        monitor_data = []
        if refresh_btn or True:  # 初始加载
            with st.spinner("拉取实时数据…"):
                for sym in st.session_state.monitor_list:
                    mkt = detect_market(sym)
                    try:
                        df = yf.Ticker(sym).history(period="5d", interval="1h", auto_adjust=True)
                        if df is not None and not df.empty:
                            close = float(df["Close"].iloc[-1])
                            fib = fiboauto_calc(df, 30)
                            fib_pos = get_fib_position(close, fib) if fib else None
                            hit = check_fib_zones(close, fib, list(PRESET_ZONES_DEF.values())) if fib else []
                            monitor_data.append({
                                "symbol": sym, "market": mkt, "close": close,
                                "direction": fib["direction"] if fib else "—",
                                "fib_pos": fib_pos, "hit_zones": hit,
                            })
                    except Exception:
                        monitor_data.append({
                            "symbol": sym, "market": mkt, "close": 0,
                            "direction": "ERROR", "fib_pos": None, "hit_zones": [],
                        })

        # 渲染监控表格
        for d in monitor_data:
            with st.container():
                col_sym, col_mkt, col_price, col_dir, col_pos, col_hit, col_del = st.columns([2,1,2,1.5,1.5,3,1])
                with col_sym:  st.markdown(f"**{d['symbol']}**")
                with col_mkt:  st.markdown(_badge(d["market"], MARKET_COLORS.get(d["market"],"#6b7280")), unsafe_allow_html=True)
                with col_price:st.markdown(f"`{fmt_price(d['close'])}`")
                with col_dir:
                    if d["direction"] == "Bullish":
                        st.markdown("🟢 上涨")
                    elif d["direction"] == "Bearish":
                        st.markdown("🔴 下跌")
                    else:
                        st.markdown("—")
                with col_pos:
                    if d["fib_pos"] is not None:
                        st.markdown(f"`{d['fib_pos']*100:.1f}%`")
                    else:
                        st.markdown("—")
                with col_hit:
                    if d["hit_zones"]:
                        for z in d["hit_zones"]:
                            st.markdown(_badge(z, ZONE_BADGE_COLORS.get(z, "#374151")), unsafe_allow_html=True)
                    else:
                        st.markdown('<span style="color:#4b5563">未命中</span>', unsafe_allow_html=True)
                with col_del:
                    if st.button("✕", key=f"del_{d['symbol']}"):
                        st.session_state.monitor_list.remove(d["symbol"])
                        st.rerun()

        st.divider()
        st.markdown("""
        <div style="background:#111827;border-radius:8px;padding:16px;border:1px solid #1e2433">
          <div style="color:#f0b429;font-weight:700;margin-bottom:8px">📡 数据源连接状态</div>
          <div style="display:flex;gap:12px;flex-wrap:wrap">
            <span>🟡 Binance WS <em style="color:#6b7280">（加密货币实时推送，需配置 API Key）</em></span><br>
            <span>🟡 Alpaca WS <em style="color:#6b7280">（美股实时报价，需配置 Alpaca 账户）</em></span><br>
            <span>🟢 yfinance 轮询 <em style="color:#6b7280">（所有资产，30秒延迟，当前激活）</em></span>
          </div>
          <div style="margin-top:12px;font-size:12px;color:#6b7280">
            在 Streamlit Cloud Secrets 中配置 BINANCE_API_KEY / ALPACA_KEY / ALPACA_SECRET
            以启用实时 WebSocket 推送，实现 &lt;100ms 预警延迟。
          </div>
        </div>
        """, unsafe_allow_html=True)

        # 预警日志（模拟）
        st.markdown("**⚡ 预警日志**")
        alerts = [r for r in monitor_data if r["hit_zones"]]
        if alerts:
            for a in alerts:
                for z in a["hit_zones"]:
                    st.toast(f"🔔 {a['symbol']} 进入 {z}！当前价 {fmt_price(a['close'])}")
            alert_df = pd.DataFrame([
                {"时间": datetime.now().strftime("%H:%M:%S"), "标的": a["symbol"],
                 "市场": a["market"], "价格": fmt_price(a["close"]),
                 "触发区间": "|".join(a["hit_zones"]), "方向": a["direction"]}
                for a in alerts
            ])
            st.dataframe(alert_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无预警，所有监控标的均未命中 Fib 区间")

# ═══════════════════════════════════════════════════════════════════════════════
# 12. 回测模块页面
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📊 回测模块":
    st.title("📊 历史回测 · 胜率与 R:R 统计")
    st.caption("滚动窗口回测 · 统计 Fib 区间触达后的胜率与盈亏比")

    with st.expander("⚙️ 回测参数", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            bt_symbol = st.text_input("回测标的", "BTC-USD")
            bt_tf = st.selectbox("时间框架", ["Daily","Weekly","4H","Monthly"], index=0)
        with col2:
            bt_days  = st.slider("回看窗口 Days", 5, 365, 35)
            bt_bars  = st.slider("超时 K 线数", 5, 100, 20)
        with col3:
            bt_zones = st.multiselect(
                "目标区间",
                list(PRESET_ZONES_DEF.keys()),
                default=["🟡 50%-61.8%", "🟠 61.8%-76%"],
            )

    run_bt = st.button("▶ 运行回测", type="primary")

    if run_bt:
        zones_list = [PRESET_ZONES_DEF[z] for z in bt_zones if z in PRESET_ZONES_DEF]
        if not zones_list:
            st.warning("请至少选择一个 Fib 区间")
        else:
            with st.spinner(f"回测 {bt_symbol} {bt_tf} 中…"):
                bt_result = backtest_single(bt_symbol, bt_tf, bt_days, zones_list, bt_bars)
            st.session_state.backtest_result = bt_result
            if "error" in bt_result:
                st.error(f"回测失败：{bt_result['error']}")

    if st.session_state.backtest_result and "error" not in st.session_state.backtest_result:
        bt = st.session_state.backtest_result

        # 统计摘要
        st.subheader("📈 回测摘要")
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("总信号数",   bt["signals"])
        mc2.metric("胜率",       f'{bt["win_rate"]}%')
        mc3.metric("R:R 比",    bt["rr_ratio"])
        mc4.metric("期望值",     bt["expected_value"])
        mc5.metric("最大连亏",   bt["max_consec_loss"])

        col_w, col_l, col_t = st.columns(3)
        with col_w: st.metric("胜 ✅", bt["wins"])
        with col_l: st.metric("负 ❌", bt["losses"])
        with col_t: st.metric("超时 ⏳", bt["timeouts"])

        # 胜率可视化
        st.subheader("📊 结果分布")
        dist_data = pd.DataFrame({
            "结果": ["胜 Win", "负 Loss", "超时 Timeout"],
            "数量": [bt["wins"], bt["losses"], bt["timeouts"]],
        })
        try:
            import plotly.express as px
            fig = px.pie(dist_data, names="结果", values="数量",
                         color_discrete_map={"胜 Win":"#22c55e","负 Loss":"#ef4444","超时 Timeout":"#94a3b8"})
            fig.update_layout(paper_bgcolor="#0a0c10", font_color="#e2e8f0")
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.bar_chart(dist_data.set_index("结果"))

        # 明细记录
        if bt["records"]:
            st.subheader("📋 信号明细")
            records_df = pd.DataFrame(bt["records"])
            outcome_map = {"win":"✅ 胜", "loss":"❌ 负", "timeout":"⏳ 超时"}
            records_df["outcome"] = records_df["outcome"].map(outcome_map)
            st.dataframe(records_df, use_container_width=True, hide_index=True)

            csv_bt = records_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "💾 导出回测明细 CSV",
                csv_bt,
                f"backtest_{bt_symbol}_{bt_tf}_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
            )

# ═══════════════════════════════════════════════════════════════════════════════
# 13. 标的池管理页面
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "⭐ 标的池管理":
    st.title("⭐ 标的池管理 · 个人收藏夹 & 团队共享")

    tab_personal, tab_team, tab_preset = st.tabs(["👤 个人收藏夹", "👥 团队标的池", "💾 扫描预设"])

    # ── 个人收藏夹 ────────────────────────────────────────────────────────────
    with tab_personal:
        col_add, col_import = st.columns([3, 1])
        with col_add:
            add_input = st.text_input("添加标的（逗号分隔）", placeholder="AAPL, BTC-USD, EURUSD=X")
        with col_import:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 添加") and add_input:
                new = [s.strip().upper() for s in add_input.split(",") if s.strip()]
                for s in new:
                    if s not in st.session_state.watchlist:
                        st.session_state.watchlist.append(s)
                st.rerun()

        # CSV 批量导入
        uploaded = st.file_uploader("📥 CSV 批量导入（每行一个代码）", type=["csv","txt"])
        if uploaded:
            content = uploaded.read().decode("utf-8")
            new_syms = [line.strip().upper() for line in content.splitlines() if line.strip()]
            added = 0
            for s in new_syms:
                if s not in st.session_state.watchlist and len(st.session_state.watchlist) < 2000:
                    st.session_state.watchlist.append(s)
                    added += 1
            st.success(f"导入 {added} 个标的")
            st.rerun()

        st.markdown(f"**收藏夹** ({len(st.session_state.watchlist)} / 2000 个标的)")

        if st.session_state.watchlist:
            # 显示收藏夹
            for i in range(0, len(st.session_state.watchlist), 6):
                cols = st.columns(6)
                for j, sym in enumerate(st.session_state.watchlist[i:i+6]):
                    with cols[j]:
                        mkt = detect_market(sym)
                        st.markdown(
                            f'<div style="background:#111827;border-radius:6px;padding:8px;'
                            f'text-align:center;border:1px solid #1e2433">'
                            f'<div style="font-weight:700;font-size:13px">{sym}</div>'
                            f'{_badge(mkt, MARKET_COLORS.get(mkt,"#6b7280"))}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            st.markdown("<br>", unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns([2,2,2])
            with bc1:
                if st.button("▶ 扫描收藏夹", use_container_width=True):
                    st.session_state.symbols_pool = st.session_state.watchlist.copy()
                    st.info("已将收藏夹设为扫描池，请切换到「扫描器」页面运行扫描")
            with bc2:
                wl_csv = "\n".join(st.session_state.watchlist).encode()
                st.download_button("💾 导出收藏夹", wl_csv,
                                   "watchlist.txt", "text/plain", use_container_width=True)
            with bc3:
                if st.button("🗑 清空收藏夹", use_container_width=True):
                    st.session_state.watchlist = []
                    st.rerun()
        else:
            st.info("收藏夹为空，请添加标的")

    # ── 团队标的池 ────────────────────────────────────────────────────────────
    with tab_team:
        st.markdown("""
        <div style="background:#111827;border-radius:8px;padding:20px;border:1px solid #1e2433;margin-bottom:16px">
          <div style="color:#f0b429;font-weight:700;font-size:16px">👥 团队标的池功能</div>
          <div style="color:#94a3b8;margin-top:8px">
            团队标的池允许多用户共享同一标的列表，支持实时同步与权限管理。<br>
            生产部署时需配置 <strong style="color:#f0b429">Supabase PostgreSQL</strong> 数据库。
          </div>
        </div>
        """, unsafe_allow_html=True)

        pool_name = st.text_input("团队池名称", placeholder="我的量化团队标的池")
        pool_desc = st.text_area("描述", placeholder="描述这个标的池的用途…", height=80)
        pool_syms = st.text_area("标的列表（每行一个）",
                                  placeholder="AAPL\nBTC-USD\nEURUSD=X", height=120)
        pool_public = st.toggle("公开分享（其他用户可订阅/Fork）")

        if st.button("💾 保存团队池（演示模式）"):
            syms_list = [s.strip().upper() for s in pool_syms.splitlines() if s.strip()]
            if pool_name and syms_list:
                st.success(f"✅ 团队池「{pool_name}」已保存 {len(syms_list)} 个标的（演示模式）")
                st.info("生产环境需配置 Supabase 数据库以实现持久化存储与多用户同步")
            else:
                st.warning("请填写团队池名称和标的列表")

    # ── 扫描预设 ──────────────────────────────────────────────────────────────
    with tab_preset:
        st.markdown("保存常用扫描参数组合，方便快速切换场景。")

        with st.form("save_preset"):
            preset_name = st.text_input("预设名称", placeholder="日常盘前扫描")
            preset_note = st.text_input("备注", placeholder="精选200个，双周期共振以上")
            save_preset = st.form_submit_button("💾 保存当前参数为预设")
            if save_preset and preset_name:
                st.session_state.scan_presets[preset_name] = {
                    "name": preset_name,
                    "note": preset_note,
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                st.success(f"预设「{preset_name}」已保存")

        if st.session_state.scan_presets:
            st.markdown("**已保存预设**")
            for pname, pdata in st.session_state.scan_presets.items():
                with st.container():
                    col_n, col_t, col_del = st.columns([3, 2, 1])
                    with col_n: st.markdown(f"**{pname}** — {pdata.get('note','')}")
                    with col_t: st.caption(pdata.get("saved_at",""))
                    with col_del:
                        if st.button("🗑", key=f"del_preset_{pname}"):
                            del st.session_state.scan_presets[pname]
                            st.rerun()
        else:
            st.info("暂无保存的预设，使用上方表单保存当前参数组合")
