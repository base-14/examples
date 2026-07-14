from runbook_assistant.cost import calculate_cost


def test_known_model_cost():
    cost = calculate_cost("claude-sonnet-4-6", 1000, 1000)
    assert abs(cost - (1000 * 3 + 1000 * 15) / 1_000_000) < 1e-9


def test_dated_model_id_normalizes():
    assert calculate_cost("claude-sonnet-4-6-20260101", 1000, 0) > 0


def test_unknown_model_is_zero():
    assert calculate_cost("mystery-model", 1000, 1000) == 0.0
