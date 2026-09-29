from decimal import Decimal

import pytest

from engine.us30_session_map import (
    Classification,
    Source,
    build_snapshot_2026_09_29,
    missing,
    observed,
    render_markdown,
    validate_levels,
)


def test_snapshot_has_auditable_core_and_exact_midpoint():
    levels = build_snapshot_2026_09_29()
    by_id = {level.identifier: level for level in levels}

    assert by_id["PX"].classification is Classification.OBSERVED
    assert by_id["PX"].value == Decimal("51365.36")
    assert by_id["S-MID"].classification is Classification.DERIVED
    assert by_id["S-MID"].value == Decimal("51317.19")
    assert by_id["S-MID"].inputs == ("S-H", "S-L")
    assert by_id["ON-H"].is_missing
    assert "does not trade overnight" in by_id["ON-H"].missing_reason
    assert by_id["VWAP"].is_missing


def test_snapshot_renders_missing_instead_of_a_proxy_value():
    report = render_markdown(build_snapshot_2026_09_29())

    assert "| OR30-H | Opening-range high (30 min) | **MISSING**" in report
    assert "| VWAP | Regular-session VWAP | **MISSING**" in report
    assert "| S-MID | Session midpoint | 51,317.19 | derived" in report
    assert "Conditional structural references" in report


def test_validation_rejects_an_observed_level_without_provenance():
    source = Source("source", "https://example.test", "2026-09-29T00:00:00Z", "test")
    level = observed("X", "test", "1.00", source, "test")
    malformed = level.__class__(
        identifier=level.identifier,
        label=level.label,
        value=level.value,
        classification=level.classification,
        source=None,
        definition=level.definition,
    )

    with pytest.raises(ValueError, match="classification and a source"):
        validate_levels((malformed,))


def test_validation_rejects_a_missing_level_with_fake_source():
    level = missing("X", "missing", "test", "no data")
    source = Source("source", "https://example.test", "2026-09-29T00:00:00Z", "test")
    malformed = level.__class__(
        identifier=level.identifier,
        label=level.label,
        value=level.value,
        classification=level.classification,
        source=source,
        definition=level.definition,
        missing_reason=level.missing_reason,
    )

    with pytest.raises(ValueError, match="Missing level"):
        validate_levels((malformed,))
