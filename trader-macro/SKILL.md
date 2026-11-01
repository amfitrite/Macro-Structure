---
name: trader-macro
description: >-
  Dual-Engine Macro & Gold Forecast. Bridges US Equities sentiment (Megabanks JPM/BAC & Big Tech)
  against the 6 Counter-DXY currency regions (EUR, JPY, GBP, CAD, SEK, CHF), diagnosing
  the Net Macro Differential, DXY momentum, and generating directional Gold (XAU/USD) forecasts.
  Use when the user asks "korelasi saham ke DXY", "pengaruh saham US ke dollar", "saham kontra DXY",
  "forecast gold", "prediksi xauusd", "kondisi makro hari ini", or "macro forecast".
argument-hint: "[--write] [--json]"
---

# trader-macro

`trader-macro` is a Quantitative Multi-Factor Macro Transmission & Dual-Engine Equity Flow Engine connecting real foreign exchange currencies, Treasury yields, and cross-border equity capital flows to Gold (XAU/USD):

1. **ICE DXY Currency Basket (Real FX Rates)**:
   - [EU] `EUR/USD` [57.6% DXY weight, exponent -0.576]
   - [JP] `USD/JPY` [13.6% DXY weight, exponent +0.136]
   - [UK] `GBP/USD` [11.9% DXY weight, exponent -0.119]
   - [CA] `USD/CAD` [9.1% DXY weight, exponent +0.091]
   - [SE] `USD/SEK` [4.2% DXY weight, exponent +0.042]
   - [CH] `USD/CHF` [3.6% DXY weight, exponent +0.036]

2. **Real Macro Yields & Opportunity Cost**:
   - `^TNX` (US 10-Year Treasury Yield): Key driver of gold non-yielding holding cost.
   - `DX-Y.NYB` (US Dollar Index): Actual benchmark currency index price.
   - `SPY` (S&P 500 ETF): Global equity risk appetite indicator.

3. **Global Equity Flow Spread (Dual Engines)**:
   - **Mesin A (US Dollar Equity Magnet)**: Megabanks (`JPM`, `BAC`) and Big Tech (`NVDA`, `MSFT`, `AAPL`).
   - **Mesin B (Counter-DXY Equity Basket)**: Regional anchors (`ASML`, `DB`, `MUFG`, `BCS`, `CNQ`, `ERIC`, `UBS`).

4. **Safe-Haven Convergence (Crisis Risk-Off Dynamics)**:
   - When panics hit the market, investors seek dollar liquidity (DXY rises) while simultaneously fleeing into Treasuries (yields drop) and Gold.
   - The engine correctly diagnoses `SAFE_HAVEN_CONVERGENCE` to prevent false-short signals during safe-haven rushes.

Tool in this folder (standard library Python, zero external dependencies):

```bash
python3 "${CLAUDE_SKILL_DIR}/forecast.py"          # Visual terminal macro & gold analysis
python3 "${CLAUDE_SKILL_DIR}/forecast.py" --write  # Saves result to trader/gold_forecast.json
python3 "${CLAUDE_SKILL_DIR}/forecast.py" --json   # Pure JSON output
```

## Quick Launcher

On Windows, double-click the desktop shortcut `Macro Gold & DXY Forecast` or run:
```bash
"${CLAUDE_SKILL_DIR}/run_macro_forecast.bat"
```

## What It Reads and Writes

| file | what |
| :--- | :--- |
| `trader/portfolio.json` *(optional)* | Read tickers held by the user to monitor correlation |
| `trader/gold_forecast.json` *(written with `--write`)* | Latest regime diagnosis, Net Differential, DXY bias, Gold forecast, and key support/resistance levels |

## Quantitative Macro Regimes

| Rezim | Kondisi Makro & Valas | Bias DXY | Gold Forecast | Sinyal Emas |
| :--- | :--- | :--- | :--- | :--- |
| **Safe-Haven Convergence** | DXY naik, Yield anjlok, Saham jatuh | Cash Preference | **STRONG BULLISH** | BUY ON DIPS / ACCUMULATION |
| **Dual Macro Headwinds** | DXY naik $+0.10\%$ & Yield naik $+0.20\%$ | Strong Bullish | **STRONG BEARISH** | STRONG SELL / SHORT |
| **Dual Macro Tailwinds** | DXY turun $-0.10\%$ & Yield turun $-0.20\%$ | Strong Bearish | **STRONG BULLISH** | STRONG BUY / LONG |
| **Dollar-Dominated Headwind** | DXY naik $\ge +0.10\%$, Yield stabil | Mild Bullish | **MILD BEARISH** | SELL ON RALLIES |
| **Dollar-Weakness Tailwind** | DXY turun $\le -0.10\%$, Yield stabil | Mild Bearish | **MILD BULLISH** | BUY ON DIPS |
| **Yield-Dominated Pressure** | Yield naik $\ge +0.20\%$, DXY stabil | Rates Focused | **MILD BEARISH** | SELL ON RALLIES |
| **Yield-Drop Tailwind** | Yield turun $\le -0.20\%$, DXY stabil | Rates Focused | **MILD BULLISH** | BUY ON DIPS |
| **Macro Equilibrium** | Pergerakan DXY & Yield dalam rentang noise | Netral | **RANGE-BOUND** | RANGE / PIVOT TRADING |

## Mathematical Formulations

### 1. ICE DXY Currency Impulse

$$\Delta\text{DXY}_{\text{ICE}} \approx -0.576 \Delta\text{EURUSD} + 0.136 \Delta\text{USDJPY} - 0.119 \Delta\text{GBPUSD} + 0.091 \Delta\text{USDCAD} + 0.042 \Delta\text{USDSEK} + 0.036 \Delta\text{USDCHF}$$

### 2. Global Equity Capital Flow Spread

$$\text{Score}_{\text{Mesin B}} = \sum_{i=1}^{6} w_i \times \Delta\text{Region}_i$$

$$\text{Equity Flow Spread} = \text{Score}_{\text{Mesin A (US)}} - \text{Score}_{\text{Mesin B (Counter)}}$$

Where:
- $w_{\text{EU}} = 0.576$ (Eurozone)
- $w_{\text{JP}} = 0.136$ (Japan)
- $w_{\text{UK}} = 0.119$ (United Kingdom)
- $w_{\text{CA}} = 0.091$ (Canada)
- $w_{\text{SE}} = 0.042$ (Sweden)
- $w_{\text{CH}} = 0.036$ (Switzerland)

### 3. Strict Audit Integrity & Zero Synthetic Data

If quotes fail to fetch from primary feeds (Yahoo Finance) and secondary feeds (CNBC Global), the system flags `DATA_UNAVAILABLE` and refuses to impute 0.00% changes, preventing artificial equilibrium classifications.

## Fine Print

Not financial advice. Macro regimes and cross-border equity differentials describe historical tendencies and capital flow dynamics, not guaranteed outcomes. Always manage risk.
