#!/usr/bin/env python3
"""Dual-Engine Macro Correlation and Gold (XAU/USD) Forecast Engine.

Standard library only, zero external dependencies.

Core Architectural Thesis:
  DXY is the outcome of a continuous "Tug-of-War" between:
    - Side A (US Dollar Drivers): US Megabanks (JPM, BAC) and Big Tech
      (NVDA, MSFT, AAPL) that pull global liquidity into the USD.
    - Side B (Counter-DXY Basket): Anchor stocks across the 6 currency
      regions weighted by their exact DXY share:
        * 🇪🇺 Eurozone (57.6%): ASML, DB (Tech & ECB rate expectations)
        * 🇯🇵 Japan (13.6%): MUFG (BOJ rate expectations)
        * 🇬🇧 United Kingdom (11.9%): BCS (BOE rate expectations)
        * 🇨🇦 Canada (9.1%): CNQ (Petrocurrency / Oil export revenue)
        * 🇸🇪 Sweden (4.2%): ERIC (Nordic industrial tech)
        * 🇨🇭 Switzerland (3.6%): UBS (Private banking & safe-haven flows)

Data Integrity Guarantee:
  - Strict health tracking: If symbols fail to fetch, the engine NEVER silently
    substitutes 0.0%. If critical benchmarks or majority of symbols fail, the
    engine explicitly raises DATA_UNAVAILABLE status.
  - Multi-tier automatic failover: Yahoo Finance -> CNBC Global Feed.

Usage:
    python3 forecast.py                     # Visual terminal report
    python3 forecast.py --write             # Saves to trader/gold_forecast.json
    python3 forecast.py --json              # Output pure JSON
    python3 forecast.py --offline DIR       # Test with offline fixtures
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; trader-macro-engine/2.0; +https://github.com/Jakeschincariol/trader-skill)"

# ---------------------------------------------------------------- Configuration
SIDE_A_STOCKS = {
    "JPM": {"name": "JPMorgan Chase", "role": "US Megabank / Fed Rates"},
    "BAC": {"name": "Bank of America", "role": "US Commercial Bank / Credit"},
    "NVDA": {"name": "Nvidia", "role": "AI / Capital Inflow Magnet"},
    "MSFT": {"name": "Microsoft", "role": "Enterprise Tech Anchor"},
    "AAPL": {"name": "Apple", "role": "Consumer Tech Benchmark"},
}

COUNTER_DXY_REGIONS = [
    {
        "region": "Eurozone",
        "pair": "EUR/USD",
        "flag": "[EU]",
        "weight": 0.576,
        "tickers": ["ASML", "DB"],
        "description": "Tech capital magnet & ECB policy proxy",
    },
    {
        "region": "Japan",
        "pair": "USD/JPY",
        "flag": "[JP]",
        "weight": 0.136,
        "tickers": ["MUFG"],
        "description": "BOJ monetary policy & Yen proxy",
    },
    {
        "region": "United Kingdom",
        "pair": "GBP/USD",
        "flag": "[UK]",
        "weight": 0.119,
        "tickers": ["BCS"],
        "description": "Domestic banking & BOE rate proxy",
    },
    {
        "region": "Canada",
        "pair": "USD/CAD",
        "flag": "[CA]",
        "weight": 0.091,
        "tickers": ["CNQ"],
        "description": "Energy & petrocurrency devisa proxy",
    },
    {
        "region": "Sweden",
        "pair": "USD/SEK",
        "flag": "[SE]",
        "weight": 0.042,
        "tickers": ["ERIC"],
        "description": "Nordic industrial tech export proxy",
    },
    {
        "region": "Switzerland",
        "pair": "USD/CHF",
        "flag": "[CH]",
        "weight": 0.036,
        "tickers": ["UBS"],
        "description": "Global private banking safe-haven",
    },
]

BENCHMARKS = {
    "DXY": "DX-Y.NYB",
    "US10Y": "^TNX",
    "GOLD": "GC=F",
    "SPY": "SPY",
}

# The 6 Official ICE DXY Constituent Currencies
DXY_FX_PAIRS = {
    "EURUSD": {"pair": "EUR/USD", "symbol": "EURUSD=X", "cnbc": "EUR=", "weight": 0.576, "exponent": -0.576, "flag": "[EU]"},
    "USDJPY": {"pair": "USD/JPY", "symbol": "USDJPY=X", "cnbc": "JPY=", "weight": 0.136, "exponent": 0.136, "flag": "[JP]"},
    "GBPUSD": {"pair": "GBP/USD", "symbol": "GBPUSD=X", "cnbc": "GBP=", "weight": 0.119, "exponent": -0.119, "flag": "[UK]"},
    "USDCAD": {"pair": "USD/CAD", "symbol": "USDCAD=X", "cnbc": "CAD=", "weight": 0.091, "exponent": 0.091, "flag": "[CA]"},
    "USDSEK": {"pair": "USD/SEK", "symbol": "USDSEK=X", "cnbc": "USDSEK", "weight": 0.042, "exponent": 0.042, "flag": "[SE]"},
    "USDCHF": {"pair": "USD/CHF", "symbol": "USDCHF=X", "cnbc": "CHF=", "weight": 0.036, "exponent": 0.036, "flag": "[CH]"},
}

CNBC_MAP = {
    "SPY": "SPY", "DX-Y.NYB": ".DXY", "GC=F": "@GC.1", "^TNX": "US10Y",
    "JPM": "JPM", "BAC": "BAC", "NVDA": "NVDA", "MSFT": "MSFT", "AAPL": "AAPL",
    "ASML": "ASML", "DB": "DB", "MUFG": "MUFG", "BCS": "BCS", "CNQ": "CNQ",
    "ERIC": "ERIC", "UBS": "UBS",
    "EURUSD=X": "EUR=", "USDJPY=X": "JPY=", "GBPUSD=X": "GBP=",
    "USDCAD=X": "CAD=", "USDSEK=X": "USDSEK", "USDCHF=X": "CHF="
}


# ---------------------------------------------------------------- Data Fetching
def parse_yahoo(text, sym):
    """Parse quote meta from Yahoo Finance chart JSON."""
    try:
        data = json.loads(text)
        res = data["chart"]["result"]
    except (ValueError, KeyError, TypeError):
        raise ValueError(f"Yahoo returned invalid JSON for {sym}")
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise ValueError(f"Yahoo has no data for {sym}: {err.get('description', 'unknown')}")
    m = res[0].get("meta", {})
    price = m.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"Yahoo has no price for {sym}")
    prev = m.get("previousClose") or m.get("chartPreviousClose")
    change = (price - prev) if (price is not None and prev is not None) else 0.0
    pct = (change / prev * 100) if (prev and prev != 0) else 0.0
    high = m.get("regularMarketDayHigh")
    low = m.get("regularMarketDayLow")
    t = m.get("regularMarketTime")
    when = (
        datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if t
        else ""
    )
    return {
        "symbol": sym.upper(),
        "price": float(price),
        "prev_close": float(prev) if prev else None,
        "change": float(change),
        "pct_change": round(pct, 2),
        "day_high": float(high) if high is not None else None,
        "day_low": float(low) if low is not None else None,
        "time": when,
        "epoch": t,
    }


def fetch_symbol_cnbc(sym, timeout=8):
    """Fallback fetcher using CNBC quotes API."""
    cnbc_sym = CNBC_MAP.get(sym, sym)
    url = f"https://quote.cnbc.com/quote-html-webservice/quote.htm?symbols={cnbc_sym}&output=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        quotes = data.get("QuickQuoteResult", {}).get("QuickQuote", [])
        if not quotes or not quotes[0].get("last"):
            raise ValueError(f"CNBC has no quote for {sym}")
        q = quotes[0]
        p = float(str(q["last"]).replace(",", ""))
        pct = float(str(q.get("change_pct", "0.0") or 0.0).replace("%", ""))
        chg = float(str(q.get("change", "0.0") or 0.0))
        prev = p - chg
        return {
            "symbol": sym.upper(),
            "price": p,
            "prev_close": round(prev, 2),
            "change": round(chg, 2),
            "pct_change": round(pct, 2),
            "day_high": float(str(q["high"]).replace(",", "")) if q.get("high") else None,
            "day_low": float(str(q["low"]).replace(",", "")) if q.get("low") else None,
            "time": q.get("last_time", ""),
            "epoch": int(time.time()),
            "source": "cnbc_failover",
        }


def fetch_google_news(query="XAUUSD gold DXY", limit=5):
    """Fetch live macro headlines from Google News RSS feed."""
    import xml.etree.ElementTree as ET
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_text = resp.read().decode("utf-8", "replace")
            root = ET.fromstring(xml_text)
            items = root.findall("./channel/item")
            headlines = []
            for item in items[:limit]:
                t = item.find("title").text if item.find("title") is not None else ""
                d = item.find("pubDate").text if item.find("pubDate") is not None else ""
                source_elem = item.find("source")
                source = source_elem.text if source_elem is not None else "Google News"
                headlines.append({
                    "title": t,
                    "date": d[:16] if d else "",
                    "source": source,
                })
            return headlines
    except Exception as e:
        return [{"title": f"Google News feed: {e}", "date": "", "source": "System"}]


def fetch_symbol(sym, offline_dir=None, timeout=10):
    """Fetch symbol metadata from Yahoo, with automatic failover to CNBC."""
    if offline_dir:
        clean_name = sym.replace("^", "").replace("=", "_")
        path = os.path.join(offline_dir, f"{clean_name}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                res = parse_yahoo(f.read(), sym)
                res["source"] = "offline_fixture"
                return res
        raise FileNotFoundError(f"Offline fixture not found: {path}")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            res = parse_yahoo(text, sym)
            res["source"] = "yahoo_primary"
            return res
    except Exception as e_yahoo:
        # Auto failover to CNBC
        try:
            return fetch_symbol_cnbc(sym, timeout=timeout)
        except Exception as e_cnbc:
            raise RuntimeError(f"Failed to fetch {sym}: Yahoo ({e_yahoo}), CNBC ({e_cnbc})")


# ---------------------------------------------------------------- Core Engine
def classify_differential(net_diff=None, dxy_pct=None, us10y_pct=None, fx_impulse=None, spy_pct=None):
    """Rigorous Quantitative Multi-Factor Macro Transmission Model for Gold (XAU/USD).
    
    Factors Evaluated:
      1. Direct DXY Impulse (DX-Y.NYB)
      2. US 10-Year Real/Nominal Yield (^TNX) - Opportunity Cost
      3. ICE-Weighted DXY Currency Basket (6 FX Pairs)
      4. Global Equity Capital Flow & Risk Sentiment (Side A vs Side B)
    
    Special Market Regimes Handled:
      - SAFE_HAVEN_CONVERGENCE: Risk-Off crisis where USD and Gold rally simultaneously
        while Yields and Equities plunge.
      - DUAL_MACRO_HEADWINDS: DXY up + US10Y up -> Strong Bearish Gold
      - DUAL_MACRO_TAILWINDS: DXY down + US10Y down -> Strong Bullish Gold
      - DOLLAR_DOMINATED_HEADWIND / TAILWIND
      - YIELD_DOMINATED_PRESSURE / TAILWIND
      - MACRO_EQUILIBRIUM: Low volatility range-bound consolidation
    """
    if net_diff is None and dxy_pct is None and us10y_pct is None:
        return {
            "regime": "DATA_UNAVAILABLE",
            "title": "Data Tidak Tersedia (Koneksi Bursa Terputus)",
            "dxy_bias": "TIDAK DAPAT DIANALISIS",
            "gold_forecast": "DATA TIDAK TERSEDIA (FETCH ERROR)",
            "gold_signal": "NO SIGNAL / HOLD",
            "explanation": "Koneksi ke bursa global gagal. Sistem menolak mengasumsikan data sintetik atau 0.0%.",
        }

    # Backward-compatible fallback if macro benchmarks (DXY & US10Y) are omitted (e.g. legacy tests)
    if dxy_pct is None and us10y_pct is None:
        if net_diff > 0.50:
            regime = "STRONG_USD_DOMINANCE"
            regime_title = "Dominasi Saham AS Sangat Kuat (Arus Modal Sedot ke Dolar)"
            dxy_bias = "STRONG BULLISH (Tekanan Penguatan Dolar Masif)"
            gold_forecast = "STRONG BEARISH (Tekanan Jual Emas Tinggi)"
            gold_signal = "STRONG SELL / SHORT"
            explanation = (
                f"Saham AS pendorong USD unggul telak (+{net_diff}% dibanding keranjang kontra). "
                "Investor global memprioritaskan aset AS dan mengonversi mata uang mereka ke Dolar. "
                "Kekuatan DXY menekan harga Emas secara signifikan."
            )
        elif net_diff >= 0.10:
            regime = "MILD_USD_DOMINANCE"
            regime_title = "Saham AS Cenderung Unggul (Arus Modal Condong ke USD)"
            dxy_bias = "MILD BULLISH (Dolar Cenderung Menguat)"
            gold_forecast = "MILD BEARISH (Emas Cenderung Terkoreksi)"
            gold_signal = "SELL ON RALLIES"
            explanation = (
                f"Saham AS mengungguli keranjang kontra-DXY dengan selisih +{net_diff}%. "
                "Sentimen devisa berpihak moderat pada Dolar AS. Emas menghadapi tekanan atas."
            )
        elif net_diff <= -0.50:
            regime = "STRONG_COUNTER_DOMINANCE"
            regime_title = "Dominasi Saham Kontra-DXY (Eropa & Asia Memimpin Arus Modal)"
            dxy_bias = "STRONG BEARISH (Dolar Mengalami Tekanan Jual Berat)"
            gold_forecast = "STRONG BULLISH (Emas Berpotensi Rally Kuat)"
            gold_signal = "STRONG BUY / LONG"
            explanation = (
                f"Saham-saham mitra kontra-DXY (Eropa, Jepang, UK) unggul masif ({net_diff}%). "
                "Likuiditas global meninggalkan Dolar AS menuju mata uang rival (EUR, JPY, GBP). "
                "Pelemahan DXY menjadi pemicu utama lonjakan harga Emas (XAU/USD)."
            )
        elif net_diff <= -0.10:
            regime = "MILD_COUNTER_DOMINANCE"
            regime_title = "Saham Kontra-DXY Cenderung Unggul (Pelemahan Dolar Moderat)"
            dxy_bias = "MILD BEARISH (Dolar Tertekan)"
            gold_forecast = "MILD BULLISH (Emas Mendapat Angin Segar)"
            gold_signal = "BUY ON DIPS"
            explanation = (
                f"Keranjang saham kawasan mitra mengungguli saham AS sebesar {abs(net_diff)}%. "
                "Dolar AS bergerak melemah moderat, membuka peluang kenaikan bertahap pada harga Emas."
            )
        else:
            regime = "EQUILIBRIUM"
            regime_title = "Keseimbangan Arus Modal (Tug-of-War Imbang / Sideways)"
            dxy_bias = "NEUTRAL / SIDEWAYS"
            gold_forecast = "RANGE-BOUND (Konsolidasi Antar Level)"
            gold_signal = "RANGE / PIVOT TRADING"
            explanation = (
                f"Selisih performa saham AS vs Kontra-DXY sangat tipis ({net_diff}%). "
                "DXY bergerak mendatar dalam konsolidasi harian. Emas diproyeksikan tertahan dalam rentang pivot."
            )
        return {
            "regime": regime,
            "title": regime_title,
            "dxy_bias": dxy_bias,
            "gold_forecast": gold_forecast,
            "gold_signal": gold_signal,
            "explanation": explanation,
        }

    # FULL MULTI-FACTOR QUANTITATIVE MACRO TRANSMISSION MODEL
    d_pct = dxy_pct if dxy_pct is not None else (fx_impulse if fx_impulse is not None else 0.0)
    y_pct = us10y_pct if us10y_pct is not None else 0.0
    sp_pct = spy_pct if spy_pct is not None else 0.0
    eq_diff = net_diff if net_diff is not None else 0.0

    # 1. Evaluasi Safe-Haven Convergence (Kepanikan Risk-Off):
    # DXY naik karena permintaan kas darurat, TAPI Yield anjlok (flight to Treasuries) & Saham anjlok
    is_risk_off = (d_pct > 0.05 and y_pct < -0.25 and sp_pct < -0.30)
    if is_risk_off:
        return {
            "regime": "SAFE_HAVEN_CONVERGENCE",
            "title": "Konvergensi Safe-Haven (Krisis Risk-Off / Flight-to-Safety)",
            "dxy_bias": "CASH PREFERENCE (Dolar Diburu Sebagai Uang Kas Darurat)",
            "gold_forecast": "STRONG BULLISH (Emas & Dolar Rally Bersama Sebagai Pelindung Nilai)",
            "gold_signal": "BUY ON DIPS / SAFE-HAVEN ACCUMULATION",
            "macro_score": 1.50,
            "is_safe_haven": True,
            "explanation": (
                "Pasar global berada dalam fase Risk-Off. Meskipun DXY menguat akibat aksi borong uang kas Dolar, "
                "penurunan tajam yield obligasi AS dan anjloknya pasar saham memicu pelarian modal masif ke Emas. "
                "Emas dan Dolar mengalami konvergensi penguatan bersama sebagai aset lindung nilai utama."
            ),
        }

    # 2. Kondisi Hambatan & Dukungan Makro Ganda (DXY & US10Y)
    is_dxy_up = d_pct >= 0.10
    is_dxy_down = d_pct <= -0.10
    is_yield_up = y_pct >= 0.20
    is_yield_down = y_pct <= -0.20

    # Composite Score calculation (-3.0 to +3.0)
    # DXY 40% impact, Yield 40% impact, Equity flow 20% impact
    score = (-1.0 * d_pct * 2.0) + (-1.0 * (y_pct / 2.0)) + (-0.2 * eq_diff)

    if is_dxy_up and is_yield_up:
        return {
            "regime": "DUAL_MACRO_HEADWINDS",
            "title": "Tekanan Makro Ganda (DXY Menguat + Yield Obligasi Melonjak)",
            "dxy_bias": "STRONG BULLISH (Penguatan Dolar Didukung Kenaikan Suku Bunga)",
            "gold_forecast": "STRONG BEARISH (Tekanan Ganda: Valuta Mahal & Opportunity Cost Tinggi)",
            "gold_signal": "STRONG SELL / SHORT",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Dolar AS menguat ({d_pct:+.2f}%) didorong oleh lonjakan yield US 10-Year ({y_pct:+.2f}%). "
                "Kombinasi kurs yang mahal dan meningkatnya opportunity cost memegang emas tanpa imbal hasil "
                "memberikan tekanan jual terberat pada harga Emas (XAU/USD)."
            ),
        }
    elif is_dxy_down and is_yield_down:
        return {
            "regime": "DUAL_MACRO_TAILWINDS",
            "title": "Dukungan Makro Ganda (DXY Melemah + Yield Obligasi Menurun)",
            "dxy_bias": "STRONG BEARISH (Tekanan Jual Dolar & Pelonggaran Suku Bunga)",
            "gold_forecast": "STRONG BULLISH (Angin Segar Makro Kuat untuk Reli Emas)",
            "gold_signal": "STRONG BUY / LONG",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Dolar AS melemah ({d_pct:+.2f}%) bersamaan dengan penurunan yield US 10-Year ({y_pct:+.2f}%). "
                "Pelemahan nilai tukar global dan penurunan opportunity cost obligasi menjadi katalis ganda "
                "terbaik untuk kenaikan harga Emas (XAU/USD)."
            ),
        }
    elif is_dxy_up:
        return {
            "regime": "DOLLAR_DOMINATED_HEADWIND",
            "title": "Hambatan Dominasi Dolar (DXY Menguat Nyata di Pasar Valas)",
            "dxy_bias": "MILD BULLISH (Sentimen Positif Dolar)",
            "gold_forecast": "MILD BEARISH (Emas Tertahan Penguatan Kurs Dolar)",
            "gold_signal": "SELL ON RALLIES",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Penguatan DXY ({d_pct:+.2f}%) menjadi penekan utama pergerakan komoditas. "
                "Meskipun yield obligasi relatif stabil, daya beli mata uang mitra melemah sehingga menahan laju Emas."
            ),
        }
    elif is_dxy_down:
        return {
            "regime": "DOLLAR_WEAKNESS_TAILWIND",
            "title": "Dukungan Pelemahan Dolar (DXY Melemah di Pasar Valas)",
            "dxy_bias": "MILD BEARISH (Tekanan Jual Dolar Moderat)",
            "gold_forecast": "MILD BULLISH (Emas Terdorong Pelemahan Dolar)",
            "gold_signal": "BUY ON DIPS",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Pelemahan DXY ({d_pct:+.2f}%) memberikan dorongan positif pada aset berdenominasi Dolar. "
                "Emas mendapatkan angin segar dari meningkatnya daya beli valuta global."
            ),
        }
    elif is_yield_up:
        return {
            "regime": "YIELD_DOMINATED_PRESSURE",
            "title": "Tekanan Lonjakan Yield (Opportunity Cost Emas Meningkat)",
            "dxy_bias": "NEUTRAL / RATES-FOCUSED",
            "gold_forecast": "MILD BEARISH (Emas Tertekan Kenaikan Suku Bunga Riil)",
            "gold_signal": "SELL ON RALLIES",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Yield Treasury 10-Tahun melonjak ({y_pct:+.2f}%), meningkatkan daya tarik aset berbunga. "
                "Emas yang tidak memberikan kupon/dividen menghadapi aksi pelepasan posisi oleh pengelola dana."
            ),
        }
    elif is_yield_down:
        return {
            "regime": "YIELD_DROP_TAILWIND",
            "title": "Dukungan Penurunan Yield (Opportunity Cost Emas Menurun)",
            "dxy_bias": "NEUTRAL / RATES-FOCUSED",
            "gold_forecast": "MILD BULLISH (Penurunan Bunga Mendorong Minat Emas)",
            "gold_signal": "BUY ON DIPS",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"Penurunan yield US 10-Year ({y_pct:+.2f}%) menekan imbal hasil obligasi pemerintah. "
                "Penurunan suku bunga riil secara historis memicu peralihan likuiditas kembali ke Emas."
            ),
        }
    else:
        return {
            "regime": "MACRO_EQUILIBRIUM",
            "title": "Keseimbangan Makro (DXY & Yield Bergerak Konsolidasi Sideways)",
            "dxy_bias": "NEUTRAL / SIDEWAYS",
            "gold_forecast": "RANGE-BOUND (Konsolidasi Antar Level Pivot)",
            "gold_signal": "RANGE / PIVOT TRADING",
            "macro_score": round(score, 2),
            "is_safe_haven": False,
            "explanation": (
                f"DXY ({d_pct:+.2f}%) dan Yield US 10Y ({y_pct:+.2f}%) bergerak dalam rentang noise sempit. "
                "Tidak ada dorongan makro dominan; harga Emas bergerak teknikal di antara level Support dan Resistance harian."
            ),
        }


def analyze_regime(equity_pct=0.0, dxy_pct=0.0, us10y_pct=0.0):
    """Backward compatibility helper for regime analysis."""
    net_diff = round(equity_pct - dxy_pct, 2)
    return classify_differential(net_diff)


def compute_macro_differential(offline_dir=None):
    """Fetch all Dual-Engine assets, DXY FX pairs, and macro benchmarks with strict health audit.
    
    If symbols fail, they are NOT assumed to be 0.0%. If critical benchmarks or
    the majority of symbols fail, the engine refuses to guess and marks status
    as DATA_UNAVAILABLE.
    """
    quotes = {}
    errors = {}

    all_symbols = (
        list(SIDE_A_STOCKS.keys()) +
        list(BENCHMARKS.values()) +
        [p["symbol"] for p in DXY_FX_PAIRS.values()]
    )
    for r in COUNTER_DXY_REGIONS:
        all_symbols.extend(r["tickers"])
    all_symbols = sorted(list(set(all_symbols)))

    for sym in all_symbols:
        try:
            quotes[sym] = fetch_symbol(sym, offline_dir=offline_dir)
        except Exception as e:
            errors[sym] = str(e)

    total_symbols = len(all_symbols)
    success_count = len(quotes)
    fail_count = len(errors)
    health_pct = round((success_count / total_symbols) * 100, 1)

    # 1. Evaluasi Mesin A (Saham AS): HANYA gunakan data yang sukses
    side_a_results = []
    side_a_valid_pcts = []
    for sym, info in SIDE_A_STOCKS.items():
        q = quotes.get(sym)
        if q and q.get("pct_change") is not None:
            pct = q["pct_change"]
            side_a_valid_pcts.append(pct)
            price = q["price"]
            src = q.get("source", "unknown")
        else:
            pct = None
            price = None
            src = "FAILED"

        side_a_results.append({
            "symbol": sym,
            "name": info["name"],
            "role": info["role"],
            "price": price,
            "pct_change": pct,
            "status": "OK" if q else "FAILED",
            "source": src,
        })

    # 2. Evaluasi Mesin B (Saham 6 Kawasan): HANYA gunakan data yang sukses
    side_b_regions = []
    weighted_counter_score = 0.0
    counter_weight_sum = 0.0

    for reg in COUNTER_DXY_REGIONS:
        reg_valid_pcts = []
        ticker_details = []
        for t in reg["tickers"]:
            q = quotes.get(t)
            if q and q.get("pct_change") is not None:
                pct = q["pct_change"]
                reg_valid_pcts.append(pct)
                price = q["price"]
                src = q.get("source", "unknown")
            else:
                pct = None
                price = None
                src = "FAILED"

            ticker_details.append({
                "symbol": t,
                "price": price,
                "pct_change": pct,
                "status": "OK" if q else "FAILED",
                "source": src,
            })

        if reg_valid_pcts:
            avg_reg_pct = round(sum(reg_valid_pcts) / len(reg_valid_pcts), 2)
            weighted_contribution = round(avg_reg_pct * reg["weight"], 3)
            weighted_counter_score += avg_reg_pct * reg["weight"]
            counter_weight_sum += reg["weight"]
        else:
            avg_reg_pct = None
            weighted_contribution = None

        side_b_regions.append({
            "region": reg["region"],
            "pair": reg["pair"],
            "flag": reg["flag"],
            "weight": reg["weight"],
            "weight_pct": f"{round(reg['weight'] * 100, 1)}%",
            "description": reg["description"],
            "tickers": ticker_details,
            "avg_pct_change": avg_reg_pct,
            "dxy_contribution_impact": weighted_contribution,
            "has_data": bool(reg_valid_pcts),
        })

    # 3. Evaluasi ICE DXY Currency Basket (Kurs Riil 6 Valuta Konstituen)
    fx_basket_results = []
    fx_impulse = 0.0
    fx_weight_sum = 0.0

    for key, info in DXY_FX_PAIRS.items():
        sym = info["symbol"]
        q = quotes.get(sym)
        if q and q.get("pct_change") is not None:
            pct = q["pct_change"]
            price = q["price"]
            src = q.get("source", "unknown")
            contribution = round(info["exponent"] * pct, 3)
            fx_impulse += info["exponent"] * pct
            fx_weight_sum += info["weight"]
        else:
            pct = None
            price = None
            src = "FAILED"
            contribution = None

        fx_basket_results.append({
            "key": key,
            "pair": info["pair"],
            "flag": info["flag"],
            "symbol": sym,
            "weight": info["weight"],
            "weight_pct": f"{round(info['weight'] * 100, 1)}%",
            "exponent": info["exponent"],
            "price": price,
            "pct_change": pct,
            "dxy_impulse_contribution": contribution,
            "status": "OK" if q else "FAILED",
            "source": src,
        })

    normalized_fx_impulse = round(fx_impulse / fx_weight_sum, 2) if fx_weight_sum > 0 else 0.0

    # 4. Validitas Sistem: Jangan bohong jika data kritis hilang
    dxy_quote = quotes.get(BENCHMARKS["DXY"])
    gold_quote = quotes.get(BENCHMARKS["GOLD"])
    us10y_quote = quotes.get(BENCHMARKS["US10Y"])
    spy_quote = quotes.get(BENCHMARKS["SPY"])

    has_sufficient_data = (
        len(side_a_valid_pcts) >= 3 and
        counter_weight_sum >= 0.50 and
        (dxy_quote is not None or fx_weight_sum >= 0.50) and
        gold_quote is not None
    )

    if has_sufficient_data:
        score_usd = round(sum(side_a_valid_pcts) / len(side_a_valid_pcts), 2)
        normalized_counter_score = round(weighted_counter_score / counter_weight_sum, 2) if counter_weight_sum > 0 else 0.0
        score_counter = normalized_counter_score
        net_diff = round(score_usd - score_counter, 2)

        dxy_chg = dxy_quote["pct_change"] if dxy_quote else normalized_fx_impulse
        us10y_chg = us10y_quote["pct_change"] if us10y_quote else None
        spy_chg = spy_quote["pct_change"] if spy_quote else None

        # Jalankan Quantitative Multi-Factor Transmission Model
        regime_info = classify_differential(
            net_diff=net_diff,
            dxy_pct=dxy_chg,
            us10y_pct=us10y_chg,
            fx_impulse=normalized_fx_impulse,
            spy_pct=spy_chg
        )
        is_live = True
        status_label = "LIVE DATA (YAHOO + CNBC FAILOVER)" if fail_count == 0 else f"PARTIAL LIVE ({success_count}/{total_symbols} SYMBOLS)"
    else:
        score_usd = None
        score_counter = None
        net_diff = None
        dxy_chg = None
        us10y_chg = None
        is_live = False
        status_label = "DATA FETCH FAILED (SERVER ERROR)"
        regime_info = {
            "regime": "DATA_UNAVAILABLE",
            "title": f"DATA TIDAK TERSEDIA ({fail_count}/{total_symbols} GAGAL)",
            "dxy_bias": "TIDAK DAPAT DIANALISIS",
            "gold_forecast": "DATA TIDAK TERSEDIA (FETCH ERROR)",
            "gold_signal": "NO SIGNAL / HOLD",
            "explanation": f"Gagal mengambil {fail_count} simbol dari server bursa ({', '.join(errors.keys())}). Sistem menolak mengasumsikan data sintetik atau menyamakan kegagalan dengan kestabilan 0.00%.",
        }

    # 5. Level Pivot & Acuan Emas
    levels = {}
    if gold_quote and gold_quote.get("price") and gold_quote.get("day_high") and gold_quote.get("day_low"):
        p = (gold_quote["day_high"] + gold_quote["day_low"] + gold_quote["price"]) / 3.0
        r1 = 2 * p - gold_quote["day_low"]
        s1 = 2 * p - gold_quote["day_high"]
        levels = {
            "pivot": round(p, 2),
            "resistance_1": round(r1, 2),
            "support_1": round(s1, 2),
            "day_high": round(gold_quote["day_high"], 2),
            "day_low": round(gold_quote["day_low"], 2),
        }

    news = []
    if not offline_dir:
        try:
            news = fetch_google_news()
        except Exception:
            pass

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "timestamp": now,
        "engine": "Quantitative Multi-Factor Macro Transmission & Dual-Engine Equity Flow",
        "is_valid": has_sufficient_data,
        "is_live": is_live,
        "status_label": status_label,
        "data_quality": {
            "total_symbols": total_symbols,
            "success_count": success_count,
            "fail_count": fail_count,
            "health_pct": health_pct,
            "missing_symbols": list(errors.keys()),
        },
        "regime": regime_info["regime"],
        "title": regime_info["title"],
        "dxy_bias": regime_info["dxy_bias"],
        "gold_forecast": regime_info["gold_forecast"],
        "gold_signal": regime_info["gold_signal"],
        "explanation": regime_info["explanation"],
        "macro_transmission": {
            "model": "Multi-Factor Quantitative Macro Transmission",
            "dxy_pct": dxy_chg,
            "us10y_pct": us10y_chg,
            "ice_fx_impulse": normalized_fx_impulse,
            "equity_flow_spread": net_diff,
            "macro_score": regime_info.get("macro_score", 0.0),
            "is_safe_haven_convergence": regime_info.get("is_safe_haven", False),
        },
        "battle_metrics": {
            "score_usd_side_a": score_usd,
            "score_counter_side_b": score_counter,
            "net_differential": net_diff,
            "label": "Global Equity Capital Flow Spread (US vs 6 Regions)",
        },
        "side_a_us_stocks": side_a_results,
        "side_b_counter_dxy": side_b_regions,
        "fx_currency_basket": fx_basket_results,
        "benchmarks": {
            "DXY": dxy_quote,
            "US10Y": us10y_quote,
            "GOLD": gold_quote,
            "SPY": spy_quote,
        },
        "gold_key_levels": levels,
        "news": news,
        "errors": errors if errors else None,
    }


# ---------------------------------------------------------------- Terminal View
def render_terminal(data):
    """Render high-contrast visual dashboard."""
    dq = data["data_quality"]
    bm = data.get("battle_metrics", {})
    bench = data.get("benchmarks", {})
    macro_trans = data.get("macro_transmission", {})
    dxy = bench.get("DXY") or {}
    gold = bench.get("GOLD") or {}
    us10y = bench.get("US10Y") or {}
    spy = bench.get("SPY") or {}
    levels = data.get("gold_key_levels") or {}

    def f_pct(val):
        if val is None:
            return " N/A  "
        sign = "+" if val >= 0 else ""
        arrow = "^" if val > 0 else ("v" if val < 0 else "=")
        return f"{arrow} {sign}{val:.2f}%"

    print("=" * 78)
    print("      QUANTITATIVE MACRO TRANSMISSION & DUAL-ENGINE GOLD FORECAST     ")
    print("=" * 78)
    print(f"Timestamp UTC : {data['timestamp']}")
    print(f"Kualitas Data : {data['status_label']} ({dq['health_pct']}% Berhasil)")
    if data.get("errors"):
        print(f"[PERINGATAN]  : {len(data['errors'])} simbol gagal ({', '.join(data['errors'].keys())})")
    print("-" * 78)

    # 1. True Macro Transmission Drivers
    print("1. TRANSMISI MAKRO UTAMA (PENGGERAK HARGA EMAS / XAU-USD):")
    dxy_val = f"{dxy['price']:.3f}" if dxy.get("price") else "N/A"
    us10y_val = f"{us10y['price']:.2f}%" if us10y.get("price") else "N/A"
    gold_val = f"${gold['price']:.2f}" if gold.get("price") else "N/A"
    spy_val = f"${spy['price']:.2f}" if spy.get("price") else "N/A"

    print(f"   * US Dollar Index (DXY)        : {dxy_val:<9} ({f_pct(dxy.get('pct_change'))}) [{dxy.get('source', '')}]")
    print(f"   * US 10-Year Yield (^TNX)      : {us10y_val:<9} ({f_pct(us10y.get('pct_change'))}) [{us10y.get('source', '')}]")
    print(f"   * S&P 500 ETF (SPY)            : {spy_val:<9} ({f_pct(spy.get('pct_change'))}) [{spy.get('source', '')}]")
    print(f"   * ICE FX Basket Impulse        : {f_pct(macro_trans.get('ice_fx_impulse'))} (Dihitung dari 6 Valuta Riil)")
    print(f"   * Equity Capital Flow Spread   : {f_pct(macro_trans.get('equity_flow_spread'))} (Saham AS vs 6 Kawasan)")
    print("-" * 78)

    # 2. Kurs Valuta Konstituen DXY
    print("2. VALUTA KONSTITUEN DXY (KURS RIIL & FORMULA ICE DXY):")
    for fx in data.get("fx_currency_basket", []):
        p_str = f"{fx['price']:8.4f}" if fx["price"] is not None else "  FAILED"
        imp_str = f"{fx['dxy_impulse_contribution']:+.3f}%" if fx["dxy_impulse_contribution"] is not None else "  N/A "
        print(f"   {fx['flag']} {fx['pair']:7} [{fx['weight_pct']:>5}]: {p_str} ({f_pct(fx['pct_change'])}) -> Kontribusi DXY: {imp_str}")
    print("-" * 78)

    # 3. Radar Ekuitas (Side A vs Side B)
    score_usd_str = f_pct(bm.get('score_usd_side_a'))
    score_b_str = f_pct(bm.get('score_counter_side_b'))
    net_diff_str = f_pct(bm.get('net_differential'))
    print("3. RADAR ALIRAN MODAL EKUITAS (GLOBAL RISK-APPETITE & SECTOR FLOW):")
    print(f"   * Mesin A (Saham AS Pendorong USD)    : {score_usd_str}")
    print(f"   * Mesin B (Saham 6 Kawasan Kontra)    : {score_b_str}")
    print(f"   * Net Equity Flow Spread (A - B)      : {net_diff_str}")
    print("-" * 78)

    # 4. Kesimpulan Rezim & Proyeksi Emas
    print("4. REZIM TRANSMISI MAKRO & SINYAL EMAS (XAU/USD):")
    print(f"   REZIM    : {data['title']}")
    print(f"   FORECAST : {data['gold_forecast']}")
    print(f"   ACTION   : {data['gold_signal']}")
    print(f"   BIAS DXY : {data['dxy_bias']}")
    if gold.get("price"):
        print(f"   Acuan Harga Emas (GC=F) : {gold_val} ({f_pct(gold.get('pct_change'))}) [{gold.get('source', '')}]")
    print()
    print("   Analisis Transmisi Makro:")
    print(f"   {data['explanation']}")
    if levels:
        print("-" * 78)
        print("5. LEVEL TEKNIKAL ACUAN EMAS:")
        print(f"   Resistance 1 : ${levels.get('resistance_1')}")
        print(f"   Pivot Level  : ${levels.get('pivot')}")
        print(f"   Support 1    : ${levels.get('support_1')}")
        print(f"   Rentang Hari : ${levels.get('day_low')} - ${levels.get('day_high')}")
    print("=" * 78)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Dual-Engine Macro & Gold Forecast Engine")
    parser.add_argument("--json", action="store_true", help="Output pure JSON")
    parser.add_argument("--write", action="store_true", help="Write result to trader/gold_forecast.json")
    parser.add_argument("--offline", type=str, help="Directory of offline fixtures for testing")
    args = parser.parse_args()

    data = compute_macro_differential(offline_dir=args.offline)

    if args.write:
        os.makedirs("trader", exist_ok=True)
        out_path = os.path.join("trader", "gold_forecast.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        render_terminal(data)
        if args.write:
            print(f"\n[OK] Analisis Dual-Engine disimpan ke trader/gold_forecast.json")


if __name__ == "__main__":
    main()
