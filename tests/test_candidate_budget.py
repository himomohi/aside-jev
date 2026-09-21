"""Candidate parsing must never return an execution table it cannot validate."""
import pytest

from aside_jev.core import build_abstain, parse_candidates, validate_candidates


def rows_at_limit():
    # 12 * (2-character ID + 1,998-character description) = 24,000.
    return [{"id": f"{index:02}", "description": "x" * 1998} for index in range(12)]


def test_implicit_abstain_counts_towards_total_context_budget():
    with pytest.raises(ValueError, match="24000-character"):
        parse_candidates(rows_at_limit())


def test_exact_budget_without_implicit_abstain_remains_valid():
    candidates = parse_candidates(rows_at_limit(), include_abstain=False)
    validate_candidates(candidates)
    assert len(candidates) == 12


def test_exact_budget_including_abstain_is_accepted():
    rows = rows_at_limit()
    abstain = build_abstain()
    overhead = len(abstain.id) + len(abstain.description)
    rows[0]["description"] = rows[0]["description"][:-overhead]
    candidates = parse_candidates(rows)
    validate_candidates(candidates)
    assert sum(len(row.id) + len(row.description) for row in candidates) == 24000
    assert candidates[-1].id == "abstain"


def test_explicit_abstain_is_not_appended_twice():
    candidates = parse_candidates([{"id": "next"}, {"id": "abstain"}])
    assert [candidate.id for candidate in candidates] == ["next", "abstain"]


@pytest.mark.parametrize("identifier", [None, 123, True, [], {}])
def test_non_text_ids_fail_at_parsing_boundary(identifier):
    with pytest.raises(ValueError, match="candidate id"):
        parse_candidates([{"id": identifier}])
