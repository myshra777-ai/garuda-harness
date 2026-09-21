from __future__ import annotations

import pytest

from harness.budgets import BudgetExceeded, CallBudget


def test_first_call_is_allowed() -> None:
    budget = CallBudget(max_calls=1)

    budget.before_call("garuda.entities", {"workspace": "fixture"})

    assert budget.call_count == 1


def test_total_call_limit_rejects_before_transport() -> None:
    budget = CallBudget(max_calls=1)
    arguments = {"workspace": "fixture"}

    budget.before_call("garuda.entities", arguments)

    with pytest.raises(BudgetExceeded, match="maximum call budget"):
        budget.before_call("garuda.briefing", arguments)

    assert budget.call_count == 1


def test_repeated_identical_calls_are_bounded() -> None:
    budget = CallBudget(max_calls=10, max_repeated_calls=2)
    arguments = {"workspace": "fixture"}

    budget.before_call("garuda.entities", arguments)
    budget.before_call("garuda.entities", arguments)

    with pytest.raises(BudgetExceeded, match="repeated-call budget"):
        budget.before_call("garuda.entities", arguments)

    assert budget.call_count == 2


def test_different_arguments_do_not_share_repeat_budget() -> None:
    budget = CallBudget(max_calls=2, max_repeated_calls=1)

    budget.before_call("garuda.entities", {"workspace": "one"})
    budget.before_call("garuda.entities", {"workspace": "two"})

    assert budget.call_count == 2


def test_different_tools_do_not_share_repeat_budget() -> None:
    budget = CallBudget(max_calls=2, max_repeated_calls=1)
    arguments = {"workspace": "fixture"}

    budget.before_call("garuda.entities", arguments)
    budget.before_call("garuda.briefing", arguments)

    assert budget.call_count == 2


def test_argument_key_order_does_not_change_identity() -> None:
    budget = CallBudget(max_calls=3, max_repeated_calls=1)

    budget.before_call(
        "garuda.entities",
        {"workspace": "fixture", "limit": 10},
    )

    with pytest.raises(BudgetExceeded, match="repeated-call budget"):
        budget.before_call(
            "garuda.entities",
            {"limit": 10, "workspace": "fixture"},
        )


def test_oversized_result_is_rejected() -> None:
    budget = CallBudget(max_result_bytes=10)

    with pytest.raises(BudgetExceeded, match="result-size budget"):
        budget.record_result({"text": "this is too large"})


def test_result_within_limit_is_allowed() -> None:
    budget = CallBudget(max_result_bytes=100)

    budget.record_result({"status": "ok"})


def test_invalid_budget_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_calls"):
        CallBudget(max_calls=0)
    with pytest.raises(ValueError, match="max_repeated_calls"):
        CallBudget(max_repeated_calls=0)
    with pytest.raises(ValueError, match="max_result_bytes"):
        CallBudget(max_result_bytes=0)