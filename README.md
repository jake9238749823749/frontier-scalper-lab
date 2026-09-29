# frontier-scalper-lab

## Datasets

### `datasets/us30_20260929/` — US30 / Dow intraday multi-timeframe tape (LANE 2)
Source-backed intraday capture of `^DJI` at 1m / 3m / 5m / 15m / 30m, taken live during the
2026-09-29 US regular session. Raw vendor payloads are stored verbatim alongside the derived
tape, and the report is split into **VERIFIED / DERIVED / MISSING** sections.

- Report: `datasets/us30_20260929/US30_INTRADAY_TAPE.md`
- Rebuild: `python3 scripts/build_us30_intraday_dataset.py && python3 scripts/render_us30_report.py`
- Validate (offline, no deps): `python3 tests/test_us30_intraday_dataset.py`

3m has no native vendor feed and is aggregated from native 1m bars — every row carries an
`origin` column (`VERIFIED` / `DERIVED`) and a `bar_status` column (`COMPLETED` / `IN_PROGRESS`).
