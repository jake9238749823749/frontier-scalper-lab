"""Auditable US30 / DJIA cash-session map builder.

The term ``US30`` is broker-specific.  This module deliberately uses the cash
Dow Jones Industrial Average (DJIA, ^DJI) as its canonical instrument and does
not transfer a futures or CFD price into that map.  Its main job is provenance:
every populated price must retain a source, source timestamp, and one of the
allowed classifications (observed, derived, or conditional).  Fields without a
verified input stay MISSING; the builder never infers a market level.

This is intentionally dependency-free so the checked-in snapshot can be
reproduced and reviewed without a live-data library or a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable, Mapping, Optional


class Classification(str, Enum):
    """Permitted treatment of a numeric level in the map."""

    OBSERVED = "observed"
    DERIVED = "derived"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class Source:
    """An immutable citation for an observed input or a report-time note."""

    name: str
    url: str
    timestamp_utc: str
    detail: str

    def markdown(self) -> str:
        return f"[{self.name}]({self.url}) — `{self.timestamp_utc}`<br>{self.detail}"


@dataclass(frozen=True)
class Level:
    """A single map row.

    ``value`` is None only when ``missing_reason`` is populated.  This explicit
    shape prevents accidental presentation of a calculated number as observed.
    """

    identifier: str
    label: str
    value: Optional[Decimal]
    classification: Optional[Classification]
    source: Optional[Source]
    definition: str
    inputs: tuple[str, ...] = ()
    missing_reason: Optional[str] = None

    @property
    def is_missing(self) -> bool:
        return self.value is None

    def formatted_value(self) -> str:
        if self.value is None:
            return "**MISSING**"
        return f"{self.value:,.2f}"


POINT = Decimal("0.01")


def _money(value: Decimal | str | float) -> Decimal:
    """Normalize prices to two decimal places without binary-float surprises."""

    return Decimal(str(value)).quantize(POINT, rounding=ROUND_HALF_UP)


def observed(
    identifier: str,
    label: str,
    value: Decimal | str | float,
    source: Source,
    definition: str,
) -> Level:
    return Level(identifier, label, _money(value), Classification.OBSERVED, source, definition)


def derived(
    identifier: str,
    label: str,
    value: Decimal | str | float,
    source: Source,
    definition: str,
    *inputs: str,
) -> Level:
    return Level(
        identifier,
        label,
        _money(value),
        Classification.DERIVED,
        source,
        definition,
        tuple(inputs),
    )


def conditional(
    identifier: str,
    label: str,
    value: Decimal | str | float,
    source: Source,
    definition: str,
    *inputs: str,
) -> Level:
    return Level(
        identifier,
        label,
        _money(value),
        Classification.CONDITIONAL,
        source,
        definition,
        tuple(inputs),
    )


def missing(identifier: str, label: str, definition: str, reason: str) -> Level:
    return Level(
        identifier=identifier,
        label=label,
        value=None,
        classification=None,
        source=None,
        definition=definition,
        missing_reason=reason,
    )


def validate_levels(levels: Iterable[Level]) -> None:
    """Fail loudly if a snapshot violates its provenance or price invariants."""

    levels = tuple(levels)
    identifiers = [level.identifier for level in levels]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Each level identifier must be unique.")

    for level in levels:
        if level.is_missing:
            if level.classification is not None or level.source is not None or not level.missing_reason:
                raise ValueError(f"Missing level {level.identifier} must have only a reason, not a source/value.")
        elif level.classification is None or level.source is None:
            raise ValueError(f"Populated level {level.identifier} needs a classification and a source.")

    by_id = {level.identifier: level for level in levels}
    required = ("S-H", "S-L", "S-O", "PX", "S-MID", "PDH", "PDL", "PDC")
    if not all(identifier in by_id and not by_id[identifier].is_missing for identifier in required):
        return

    if by_id["S-H"].value < by_id["S-L"].value:
        raise ValueError("Session high cannot be below session low.")
    if not by_id["S-L"].value <= by_id["S-O"].value <= by_id["S-H"].value:
        raise ValueError("Cash open must lie inside the reported session range.")
    if not by_id["S-L"].value <= by_id["PX"].value <= by_id["S-H"].value:
        raise ValueError("Current cash price must lie inside the reported session range.")

    expected_mid = _money((by_id["S-H"].value + by_id["S-L"].value) / Decimal("2"))
    if by_id["S-MID"].value != expected_mid:
        raise ValueError("Session midpoint must be exactly (session high + session low) / 2.")


def build_snapshot_2026_09_29() -> tuple[Level, ...]:
    """Return the verified 2026-09-29 cash-session snapshot.

    Evidence was captured before the 16:00 EDT regular close.  The page-source
    timestamps are retained below rather than overwritten with generation time.
    Update this function only with fresh evidence; do not substitute estimates.
    """

    google_cash = Source(
        name="Google Finance — .DJI:INDEXDJX",
        url="https://www.google.com/finance/quote/.DJI:INDEXDJX",
        timestamp_utc="2026-09-29T19:37:02Z",
        detail="Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.",
    )
    yahoo_live = Source(
        name="Yahoo Finance — US market live",
        url=(
            "https://finance.yahoo.com/markets/live/stock-market-today-tuesday-"
            "september-29-dow-sp-500-nasdaq-080526442.html"
        ),
        timestamp_utc="2026-09-29T19:39:05Z",
        detail="Source-reported ^DJI last 51,365.36 at 15:39:05 EDT; market open.",
    )
    yahoo_prior = Source(
        name="Yahoo Finance — ^DJI historical prices",
        url="https://finance.yahoo.com/quote/%5EDJI/history/",
        timestamp_utc="2026-09-28T20:00:00Z",
        detail="2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.",
    )
    midpoint_calc = Source(
        name="Lane 4 calculation",
        url="https://www.google.com/finance/quote/.DJI:INDEXDJX",
        timestamp_utc="2026-09-29T19:40:34Z",
        detail="Arithmetic performed from the cited S-H and S-L values; no market-data estimate.",
    )

    session_high = observed(
        "S-H",
        "Regular-session high",
        "51505.19",
        google_cash,
        "Provider-reported DJIA cash-session high from 09:30 EDT through the source timestamp.",
    )
    session_low = observed(
        "S-L",
        "Regular-session low",
        "51129.18",
        google_cash,
        "Provider-reported DJIA cash-session low from 09:30 EDT through the source timestamp.",
    )

    levels = (
        observed(
            "PX",
            "Current cash price",
            "51365.36",
            yahoo_live,
            "Last reported ^DJI cash-index value; this is not a broker-specific US30 CFD quote.",
        ),
        observed(
            "S-O",
            "Regular-session / cash open",
            "51416.96",
            google_cash,
            "Provider-reported DJIA regular-session open at 09:30 EDT (13:30 UTC).",
        ),
        session_high,
        session_low,
        observed(
            "PDH",
            "Prior-day high",
            "51780.50",
            yahoo_prior,
            "DJIA regular-session high for Monday, 2026-09-28.",
        ),
        observed(
            "PDL",
            "Prior-day low",
            "51409.65",
            yahoo_prior,
            "DJIA regular-session low for Monday, 2026-09-28.",
        ),
        observed(
            "PDC",
            "Prior-day close",
            "51481.51",
            yahoo_prior,
            "DJIA regular-session close for Monday, 2026-09-28.",
        ),
        derived(
            "S-MID",
            "Session midpoint",
            (session_high.value + session_low.value) / Decimal("2"),
            midpoint_calc,
            "(Regular-session high + regular-session low) / 2.",
            "S-H",
            "S-L",
        ),
        # A cash index has no overnight trading.  A YM-futures range is useful
        # context only after its source and cash/futures basis are made explicit.
        missing(
            "ON-H",
            "Overnight high",
            "CME YM window 18:00 EDT (prior business day) to 09:30 EDT (cash open).",
            "No verified YM intraday series/basis adjustment was supplied. Cash ^DJI itself does not trade overnight.",
        ),
        missing(
            "ON-L",
            "Overnight low",
            "CME YM window 18:00 EDT (prior business day) to 09:30 EDT (cash open).",
            "No verified YM intraday series/basis adjustment was supplied. Cash ^DJI itself does not trade overnight.",
        ),
        missing(
            "OR30-H",
            "Opening-range high (30 min)",
            "High from 09:30:00 to 09:59:59 EDT; the convention is explicitly 30 minutes.",
            "Verified sources supplied daily/session aggregates, not 1-minute cash bars for the defined window.",
        ),
        missing(
            "OR30-L",
            "Opening-range low (30 min)",
            "Low from 09:30:00 to 09:59:59 EDT; the convention is explicitly 30 minutes.",
            "Verified sources supplied daily/session aggregates, not 1-minute cash bars for the defined window.",
        ),
        missing(
            "VWAP",
            "Regular-session VWAP",
            "Volume-weighted average price from 09:30 EDT cash open to the snapshot time.",
            "No verified intraday price-and-volume series for a defined DJIA VWAP calculation was available. Do not use a cash-index proxy or synthetic volume.",
        ),
        missing(
            "VWAP+1SD",
            "VWAP +1 standard deviation",
            "VWAP plus one volume-weighted intraday standard deviation, using the same cash-session bars.",
            "VWAP and a verified intraday price-and-volume series are MISSING.",
        ),
        missing(
            "VWAP-1SD",
            "VWAP −1 standard deviation",
            "VWAP minus one volume-weighted intraday standard deviation, using the same cash-session bars.",
            "VWAP and a verified intraday price-and-volume series are MISSING.",
        ),
        missing(
            "VWAP+2SD",
            "VWAP +2 standard deviations",
            "VWAP plus two volume-weighted intraday standard deviations, using the same cash-session bars.",
            "VWAP and a verified intraday price-and-volume series are MISSING.",
        ),
        missing(
            "VWAP-2SD",
            "VWAP −2 standard deviations",
            "VWAP minus two volume-weighted intraday standard deviations, using the same cash-session bars.",
            "VWAP and a verified intraday price-and-volume series are MISSING.",
        ),
        missing(
            "EQH",
            "Verified equal-high pool",
            "Two or more separately timestamped intraday swing highs within a declared tolerance.",
            "No verified intraday bar series was available to test equality, tolerance, or swing separation.",
        ),
        missing(
            "EQL",
            "Verified equal-low pool",
            "Two or more separately timestamped intraday swing lows within a declared tolerance.",
            "No verified intraday bar series was available to test equality, tolerance, or swing separation.",
        ),
    )
    validate_levels(levels)
    return levels


def _row(level: Level) -> str:
    if level.is_missing:
        return (
            f"| {level.identifier} | {level.label} | **MISSING** | — | "
            f"{level.definition}<br><strong>Why:</strong> {level.missing_reason} |"
        )

    assert level.classification is not None
    assert level.source is not None
    input_text = f" Inputs: {', '.join(level.inputs)}." if level.inputs else ""
    source = level.source.markdown().replace("|", "\\|")
    return (
        f"| {level.identifier} | {level.label} | {level.formatted_value()} | "
        f"{level.classification.value} | {source}<br>{level.definition}{input_text} |"
    )


def render_markdown(levels: Iterable[Level]) -> str:
    """Render a concise, reviewable map without concealing missing values."""

    levels = tuple(levels)
    by_id: Mapping[str, Level] = {level.identifier: level for level in levels}

    core_order = ("PX", "S-O", "S-H", "S-L", "PDH", "PDL", "PDC", "S-MID")
    unavailable_order = (
        "ON-H", "ON-L", "OR30-H", "OR30-L", "VWAP", "VWAP+1SD", "VWAP-1SD", "VWAP+2SD", "VWAP-2SD", "EQH", "EQL"
    )
    core_rows = "\n".join(_row(by_id[identifier]) for identifier in core_order)
    unavailable_rows = "\n".join(_row(by_id[identifier]) for identifier in unavailable_order)

    # These are intentionally conditional labels: a high/low is observable;
    # resting liquidity at that price is not.
    structural_rows = "\n".join(
        _row(
            conditional(
                f"LQ-{identifier}",
                label,
                by_id[identifier].value,
                by_id[identifier].source,  # type: ignore[arg-type]
                definition,
                identifier,
            )
        )
        for identifier, label, definition in (
            ("PDH", "Prior-day-high reference", "Conditional buy-side liquidity reference; no resting orders are asserted."),
            ("PDL", "Prior-day-low reference", "Conditional sell-side liquidity reference; no resting orders are asserted."),
            ("S-H", "Session-high reference", "Conditional buy-side liquidity reference while the session remains open."),
            ("S-L", "Session-low reference", "Conditional sell-side liquidity reference while the session remains open."),
        )
    )

    return f"""# LANE 4 — US30 Cash Session-Level Map

**Snapshot:** Tuesday, 2026-09-29, **15:39:05 EDT / 19:39:05 UTC**<br>
**Canonical instrument:** Dow Jones Industrial Average cash index (**^DJI / .DJI**), USD points.<br>
**Cash-session convention:** New York regular session, 09:30–16:00 EDT (13:30–20:00 UTC). The session was still open when captured, so current-session high/low are **as-of** values, not final settlement values.

> **Instrument control.** “US30” commonly denotes a provider-specific CFD. This map does **not** present a CME YM futures quote or a CFD quote as cash DJIA. A broker execution map needs that broker’s own bid/ask and daily-reset convention; otherwise it must remain MISSING.

## Verified price map

| ID | Level | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
{core_rows}

### Price ladder — highest to lowest

| Price | Reference |
| ---: | --- |
| 51,780.50 | Prior-day high (PDH) |
| 51,505.19 | Regular-session high (S-H) |
| 51,481.51 | Prior-day close (PDC) |
| 51,416.96 | Cash open (S-O) |
| 51,409.65 | Prior-day low (PDL) |
| 51,365.36 | Current cash price (PX) |
| 51,317.19 | Session midpoint (S-MID) |
| 51,129.18 | Regular-session low (S-L) |

## Conditional structural references

A price extreme is observable; a “liquidity pool” is an execution hypothesis. The following rows are therefore **conditional**, never an assertion that orders are resting there.

| ID | Reference | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
{structural_rows}

## Required fields that remain unverified

The 30-minute opening range is explicitly 09:30:00–09:59:59 EDT. VWAP bands mean session VWAP ± one or two *volume-weighted intraday* standard deviations; that methodology cannot be reproduced from a daily OHLC aggregate.

| ID | Level | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
{unavailable_rows}

## Source ledger and handling notes

1. **Current price:** Yahoo Finance’s live market page reported ^DJI at **51,365.36** at **15:39:05 EDT**. It is the freshest verified price used here.
2. **Current session OHLC:** Google Finance’s .DJI quote page reported the **51,416.96 / 51,505.19 / 51,129.18** open/high/low at **15:37:02 EDT**. Because the later cash price was inside that range, the cited high and low remain valid at the snapshot time; the map does not imply they were final values.
3. **Prior-day OHLC:** Yahoo Finance’s historical-price table reports the 2026-09-28 cash-session OHLC. Its close is independently consistent with the FRED DJIA daily-close series, whose source is S&P Dow Jones Indices.
4. **No silent proxies:** Cash DJIA has no overnight cash session. CME YM is a distinct futures instrument and can have a basis to cash. Overnight, OR, VWAP, VWAP deviations, and equal-high/equal-low rows stay **MISSING** until a timestamped intraday source for the exact instrument and definition is supplied.

*This is an auditable market-data map, not investment advice. Prices may differ by vendor, index dissemination latency, and any broker’s CFD spread.*
"""


def main() -> None:
    print(render_markdown(build_snapshot_2026_09_29()), end="")


if __name__ == "__main__":
    main()
