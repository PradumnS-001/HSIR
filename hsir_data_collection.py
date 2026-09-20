import pandas as pd
import yfinance as yf

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

OUT_XLSX = "HSIR_event_data.xlsx"
OUT_LONG = "HSIR_event_data_long.csv"

PRE, POST = 10, 10  # trading days either side of t0
EST_LEN, EST_GAP = 60, 1  # 60-day estimation window ending EST_GAP days before t-10

# t0 = first US trading day on which the news could be traded.
EVENTS = [
    ("E1", "US-UK strikes on Houthi targets (Red Sea)", "2024-01-11", "2024-01-12"),
    ("E2", "Iran's first direct attack on Israel", "2024-04-13", "2024-04-15"),
    ("E3", "Iranian ballistic missile barrage on Israel", "2024-10-01", "2024-10-01"),
    ("E4", "Outbreak of the Twelve-Day War", "2025-06-13", "2025-06-13"),
    ("E5", "US-Israel strikes on Iran / 2026 Iran war", "2026-02-28", "2026-03-02"),
]

BENCHMARKS = {
    "^GSPC": "SP500",
    "^VIX": "VIX",
}

# One ETF per affected sector (clean sector signal) + one bellwether stock
# (lets the write-up talk about a named firm without five-stock noise).
SECTORS = {
    "Energy": ["XLE", "XOM"],
    "Defense": ["ITA", "LMT"],
    "Airlines": ["JETS", "DAL"],
    "Controls": ["BNO", "GLD"],  # Brent oil ETF, gold
    # Optional regional-exposure bucket, uncomment to re-add:
    # "Regional": ["FRO", "ZIM", "UAE"],
}

CALENDAR_TICKER = "^GSPC"  # defines the trading calendar

# ----------------------------------------------------------------------

ALL_TICKERS = list(BENCHMARKS) + [t for v in SECTORS.values() for t in v]
TICKER_SECTOR = {
    **{t: "Benchmark" for t in BENCHMARKS},
    **{t: s for s, v in SECTORS.items() for t in v},
}
LABEL = {**BENCHMARKS, **{t: t for v in SECTORS.values() for t in v}}


def download(tickers, start, end):
    """Adjusted daily closes, one column per ticker."""
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        close.columns = tickers
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.sort_index()


def main():
    span_start = pd.Timestamp(min(t0 for *_, t0 in EVENTS)) - pd.Timedelta(
        days=int((PRE + EST_LEN + EST_GAP) * 1.7) + 30
    )
    span_end = pd.Timestamp(max(t0 for *_, t0 in EVENTS)) + pd.Timedelta(days=60)
    print(
        f"Downloading {len(ALL_TICKERS)} tickers, {span_start.date()} -> {span_end.date()} ..."
    )

    px = download(ALL_TICKERS, span_start, span_end)
    missing = [
        t for t in ALL_TICKERS if t not in px.columns or px[t].notna().sum() == 0
    ]
    if missing:
        print(f"  WARNING - no data returned for: {missing}")

    sessions = px.index[px[CALENDAR_TICKER].notna()]  # true NYSE sessions

    windows, quality, long_rows = [], [], []
    sheets = {}

    for eid, name, news_date, t0_str in EVENTS:
        t0 = pd.Timestamp(t0_str)
        if t0 not in sessions:
            print(f"  {eid}: {t0.date()} is not a trading day - check the event table.")
            continue
        i = sessions.get_loc(t0)

        est_lo = i - PRE - EST_GAP - EST_LEN + 1
        est_hi = i - PRE - EST_GAP
        lo, hi = i - PRE, i + POST
        if est_lo < 0 or hi >= len(sessions):
            print(f"  {eid}: not enough sessions around t0 in the downloaded span.")
            continue

        idx = sessions[est_lo : hi + 1]
        block = px.loc[idx, [c for c in ALL_TICKERS if c in px.columns]].copy()
        block.columns = [LABEL[c] for c in block.columns]

        rel = [sessions.get_loc(d) - i for d in idx]
        window = [
            "Estimation"
            if r < -PRE
            else ("Event day" if r == 0 else ("Pre-event" if r < 0 else "Post-event"))
            for r in rel
        ]

        sheet = pd.DataFrame({"Date": idx.date, "t": rel, "Window": window})
        sheet = pd.concat([sheet.set_index(idx), block], axis=1)

        rets = block.pct_change() * 100
        rets.columns = [f"{c}_ret%" for c in rets.columns]
        sheet = pd.concat([sheet, rets], axis=1).reset_index(drop=True)
        sheets[eid] = sheet

        windows.append(
            {
                "event_id": eid,
                "event": name,
                "news_date": news_date,
                "news_weekday": pd.Timestamp(news_date).day_name(),
                "t0": t0.date(),
                "t0_weekday": t0.day_name(),
                "est_start": idx[0].date(),
                "est_end": sessions[est_hi].date(),
                "pre_start": sessions[lo].date(),
                "post_end": sessions[hi].date(),
                "n_sessions": len(idx),
            }
        )

        for tk in ALL_TICKERS:
            if tk not in px.columns:
                continue
            col = px.loc[idx, tk]
            gaps = [str(d.date()) for d in idx[col.isna()]]
            if gaps:
                quality.append(
                    {
                        "event_id": eid,
                        "ticker": tk,
                        "n_missing": len(gaps),
                        "missing_dates": "; ".join(gaps[:15]),
                    }
                )
            for d, r in zip(idx, rel):
                long_rows.append(
                    {
                        "event_id": eid,
                        "date": d.date(),
                        "t": r,
                        "ticker": tk,
                        "sector": TICKER_SECTOR[tk],
                        "close": col.get(d),
                    }
                )

    win_df = pd.DataFrame(windows)
    qual_df = (
        pd.DataFrame(quality)
        if quality
        else pd.DataFrame(
            [{"note": "No missing observations inside any event window."}]
        )
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        win_df.to_excel(xl, sheet_name="Windows", index=False)
        for eid, sheet in sheets.items():
            sheet.to_excel(xl, sheet_name=eid, index=False)
        qual_df.to_excel(xl, sheet_name="Data_Quality", index=False)

    pd.DataFrame(long_rows).to_csv(OUT_LONG, index=False)

    print("\n" + win_df.to_string(index=False))
    print(f"\nWrote {OUT_XLSX} ({len(sheets)} event sheets) and {OUT_LONG}")
    if quality:
        print(f"{len(quality)} ticker-event gaps logged in the Data_Quality sheet.")


if __name__ == "__main__":
    main()
