#!/usr/bin/env python3
"""Sentinel Macro Monitor — Overnight signal generation.

Pulls free/delayed market data via yfinance and writes a structured
signal report to vault/finance/signals/YYYY-MM-DD.md.

Design note: data_source parameter allows swapping yfinance → IBKR
once the gateway is live (target: March 30).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip3 install yfinance", file=sys.stderr)
    sys.exit(1)


# ── Config ────────────────────────────────────────────────────────────

VAULT_SIGNALS_DIR = Path.home() / "dev" / "sentinel" / "vault" / "finance" / "signals"

TICKERS = {
    "oil": ["BNO", "USO"],
    "yields": ["^TNX", "^IRX"],
    "currency": ["UUP"],
    "crypto": ["ETH-USD", "SOL-USD", "BTC-USD", "XRP-USD"],
    "volatility": ["^VIX"],
    "equities": ["SPY", "QQQ"],
}

ALL_TICKERS = [t for group in TICKERS.values() for t in group]

# Labels for display
LABELS = {
    "BNO": "Brent (BNO)",
    "USO": "WTI (USO)",
    "^TNX": "10yr",
    "^IRX": "2yr",
    "UUP": "DXY (UUP)",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "BTC-USD": "BTC",
    "XRP-USD": "XRP",
    "^VIX": "VIX",
    "SPY": "SPY",
    "QQQ": "QQQ",
}


# ── Data fetching ─────────────────────────────────────────────────────

def fetch_yfinance_data() -> dict:
    """Fetch price data for all tickers. Returns dict keyed by ticker."""
    results = {}
    # Fetch 10 trading days of history for 5-day change calc
    tickers_str = " ".join(ALL_TICKERS)
    data = yf.download(tickers_str, period="10d", group_by="ticker", progress=False)

    for ticker in ALL_TICKERS:
        try:
            if len(ALL_TICKERS) == 1:
                df = data
            else:
                df = data[ticker] if ticker in data.columns.get_level_values(0) else None

            if df is None or df.empty or df["Close"].dropna().empty:
                results[ticker] = {"error": "no data returned"}
                print(f"  WARNING: {ticker} — no data returned", file=sys.stderr)
                continue

            closes = df["Close"].dropna()
            current = closes.iloc[-1]
            prev = closes.iloc[-2] if len(closes) >= 2 else current

            change_1d = ((current - prev) / prev) * 100 if prev != 0 else 0.0

            # 5-day change (if enough data)
            change_5d = None
            if len(closes) >= 6:
                five_ago = closes.iloc[-6]
                change_5d = ((current - five_ago) / five_ago) * 100 if five_ago != 0 else 0.0

            results[ticker] = {
                "price": float(current),
                "prev": float(prev),
                "change_1d": float(change_1d),
                "change_5d": float(change_5d) if change_5d is not None else None,
            }
        except Exception as e:
            results[ticker] = {"error": str(e)}
            print(f"  WARNING: {ticker} — {e}", file=sys.stderr)

    return results


def fetch_data(source: str = "yfinance") -> dict:
    """Fetch market data from the specified source."""
    if source == "yfinance":
        return fetch_yfinance_data()
    elif source == "ibkr":
        # Placeholder for IBKR integration (March 30)
        raise NotImplementedError("IBKR data source not yet implemented")
    else:
        raise ValueError(f"Unknown data source: {source}")


# ── Formatting helpers ────────────────────────────────────────────────

def fmt_price(val: float, decimals: int = 2) -> str:
    """Format price with comma separators."""
    if val >= 1000:
        return f"${val:,.{decimals}f}"
    return f"${val:.{decimals}f}"


def fmt_change(pct: float) -> str:
    """Format percentage change with +/- prefix."""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def fmt_bps(val: float) -> str:
    """Format basis points change."""
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.0f} bps"


def get_or_err(data: dict, ticker: str) -> Optional[dict]:
    """Get ticker data or None if error."""
    d = data.get(ticker, {})
    if "error" in d:
        return None
    return d


def err_reason(data: dict, ticker: str) -> str:
    """Get a human-readable error reason for a failed ticker."""
    d = data.get(ticker, {})
    reason = d.get("error", "unknown")
    return f"UNAVAILABLE (yfinance: {reason})"


# ── Report generation ─────────────────────────────────────────────────

def generate_report(data: dict) -> str:
    """Generate the markdown signal report from fetched data."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%d %H:%M:%S %Z").strip()

    lines = []
    lines.append(f"# Macro Signals — {date_str}")
    lines.append(f"> Generated: {ts}")
    lines.append("> Thesis: War risk / oil supply shock / stagflation / Fed bind")
    lines.append("")

    # ── Oil ──
    lines.append("## Oil")
    bno = get_or_err(data, "BNO")
    uso = get_or_err(data, "USO")
    if bno:
        line = f"- Brent (BNO): {fmt_price(bno['price'])} | {fmt_change(bno['change_1d'])} 1d"
        if bno["change_5d"] is not None:
            line += f" | {fmt_change(bno['change_5d'])} 5d"
        lines.append(line)
    else:
        lines.append(f"- Brent (BNO): {err_reason(data, 'BNO')}")

    if uso:
        lines.append(f"- WTI (USO): {fmt_price(uso['price'])} | {fmt_change(uso['change_1d'])} 1d")
    else:
        lines.append(f"- WTI (USO): {err_reason(data, 'USO')}")

    # Brent/WTI spread
    if bno and uso:
        spread = bno["price"] - uso["price"]
        prev_spread = bno["prev"] - uso["prev"]
        if spread > prev_spread + 0.05:
            trend = "widening"
        elif spread < prev_spread - 0.05:
            trend = "narrowing"
        else:
            trend = "stable"
        lines.append(f"- Brent/WTI spread: {spread:.2f} — {trend}")

    lines.append("")

    # ── Yields & Rates ──
    lines.append("## Yields & Rates")
    tnx = get_or_err(data, "^TNX")
    irx = get_or_err(data, "^IRX")

    if tnx:
        bps_1d = (tnx["price"] - tnx["prev"]) * 100  # yield is in %, bps = % * 100
        lines.append(f"- 10yr: {tnx['price']:.2f}% | {fmt_bps(bps_1d)} 1d")
    else:
        lines.append(f"- 10yr: {err_reason(data, '^TNX')}")

    if irx:
        bps_1d = (irx["price"] - irx["prev"]) * 100
        lines.append(f"- 2yr: {irx['price']:.2f}% | {fmt_bps(bps_1d)} 1d")
    else:
        lines.append(f"- 2yr: {err_reason(data, '^IRX')}")

    # 2/10 spread
    if tnx and irx:
        spread_bps = (tnx["price"] - irx["price"]) * 100
        if spread_bps < 0:
            label = "inverted"
        elif tnx["change_1d"] > irx["change_1d"]:
            label = "steepening"
        else:
            label = "flattening"
        lines.append(f"- 2/10 Spread: {fmt_bps(spread_bps)} — {label}")

    lines.append("")

    # ── Currency ──
    lines.append("## Currency")
    uup = get_or_err(data, "UUP")
    if uup:
        trend = "strengthening" if uup["change_1d"] > 0 else "weakening"
        lines.append(f"- DXY (UUP): {fmt_price(uup['price'])} | {fmt_change(uup['change_1d'])} 1d — {trend}")
    else:
        lines.append(f"- DXY (UUP): {err_reason(data, 'UUP')}")
    lines.append("")

    # ── Crypto ──
    lines.append("## Crypto (Coinbase positions)")
    for ticker in TICKERS["crypto"]:
        d = get_or_err(data, ticker)
        label = LABELS[ticker]
        if d:
            lines.append(f"- {label}: {fmt_price(d['price'])} | {fmt_change(d['change_1d'])} 1d")
        else:
            lines.append(f"- {label}: {err_reason(data, ticker)}")
    lines.append("")

    # ── Volatility & Equities ──
    lines.append("## Volatility & Equities")
    vix = get_or_err(data, "^VIX")
    if vix:
        if vix["price"] >= 30:
            vix_label = "SPIKE"
        elif vix["price"] >= 20:
            vix_label = "ELEVATED"
        else:
            vix_label = "NORMAL"
        lines.append(f"- VIX: {vix['price']:.2f} | {fmt_change(vix['change_1d'])} 1d — {vix_label}")
    else:
        lines.append(f"- VIX: {err_reason(data, '^VIX')}")

    for ticker in TICKERS["equities"]:
        d = get_or_err(data, ticker)
        label = LABELS[ticker]
        if d:
            lines.append(f"- {label}: {fmt_price(d['price'])} | {fmt_change(d['change_1d'])} 1d")
        else:
            lines.append(f"- {label}: {err_reason(data, ticker)}")
    lines.append("")

    # ── Geopolitical ──
    lines.append("## Geopolitical (web search)")
    lines.append("[PLACEHOLDER — Sentinel will fill via web search tool]")
    lines.append("")

    # ── Proactive Read ──
    lines.append("## Proactive Read")
    lines.append(_generate_proactive_read(data))
    lines.append("")

    return "\n".join(lines)


def _generate_proactive_read(data: dict) -> str:
    """Generate a data-driven proactive read based on current signals.

    This is a rule-based assessment — the NanoClaw agent will replace this
    with an LLM-generated read when it runs the task.
    """
    notes = []

    # Oil momentum
    bno = get_or_err(data, "BNO")
    if bno:
        if bno["change_1d"] > 2:
            notes.append("Oil spiking — BNO calls gaining. Watch for Hormuz/OPEC catalyst.")
        elif bno["change_1d"] < -2:
            notes.append("Oil dropping — BNO calls under pressure. Check if supply shock thesis still holds.")
        elif bno.get("change_5d") is not None and bno["change_5d"] > 5:
            notes.append("Oil trending up over 5 days — thesis intact on supply side.")

    # VIX
    vix = get_or_err(data, "^VIX")
    if vix:
        if vix["price"] >= 25:
            notes.append(f"VIX at {vix['price']:.0f} — elevated fear. VIX calls and SPY puts benefiting.")
        elif vix["price"] < 15:
            notes.append(f"VIX at {vix['price']:.0f} — complacency zone. Good entry for vol longs if thesis holds.")

    # Yield curve
    tnx = get_or_err(data, "^TNX")
    irx = get_or_err(data, "^IRX")
    if tnx and irx:
        spread = (tnx["price"] - irx["price"]) * 100
        if spread < -20:
            notes.append(f"Curve deeply inverted ({spread:.0f} bps) — recession signal still active.")
        elif spread > 0 and spread < 20:
            notes.append(f"Curve normalizing ({spread:.0f} bps) — watch for steepener if Fed pivots.")

    # Equities vs thesis
    spy = get_or_err(data, "SPY")
    if spy and spy["change_1d"] < -1.5:
        notes.append("SPY down big — puts printing. Check if this is thesis-driven or noise.")
    elif spy and spy["change_1d"] > 1.5:
        notes.append("SPY rallying — puts losing value. Re-evaluate if hedges need rolling.")

    if not notes:
        notes.append("No strong signals today. Thesis in holding pattern — stay positioned, watch oil and VIX.")

    return " ".join(notes)


# ── File output ───────────────────────────────────────────────────────

def write_report(report: str, output_dir: Optional[Path] = None) -> Path:
    """Write the report to the vault signals directory."""
    out_dir = output_dir or VAULT_SIGNALS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = out_dir / f"{date_str}.md"
    out_path.write_text(report, encoding="utf-8")
    return out_path


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sentinel Macro Monitor")
    parser.add_argument(
        "--data-source",
        choices=["yfinance", "ibkr"],
        default="yfinance",
        help="Data source (default: yfinance, ibkr available March 30)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output directory (default: vault/finance/signals/)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print report to stdout instead of writing to file",
    )
    args = parser.parse_args()

    print("Fetching market data...", file=sys.stderr)
    data = fetch_data(source=args.data_source)

    report = generate_report(data)

    if args.stdout:
        print(report)
    else:
        out_path = write_report(report, output_dir=args.output_dir)
        print(f"Written to {out_path}", file=sys.stderr)
        print(report)


if __name__ == "__main__":
    main()
