"""Unit tests for LLM-output validation (no Ollama, Redis or GPU needed)."""
import pytest
from workers.processors.validation import validate_and_parse_tasks, validate_single_task


def test_valid_task_is_accepted():
    ok, parsed, err = validate_single_task(
        {"assignee": "Asha", "task": "Send the report", "deadline": "2026-01-15", "confidence": 0.9})
    assert ok and parsed.assignee == "Asha" and err == ""


def test_missing_assignee_is_rejected():
    ok, parsed, err = validate_single_task({"task": "Send the report"})
    assert not ok and parsed is None and "assignee" in err


def test_too_short_task_is_rejected():
    ok, *_ = validate_single_task({"assignee": "Asha", "task": "hi"})
    assert not ok


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_confidence_out_of_range_is_rejected(bad):
    ok, *_ = validate_single_task({"assignee": "Asha", "task": "Send the report", "confidence": bad})
    assert not ok


def test_invalid_deadline_falls_back_to_tbd():
    ok, parsed, _ = validate_single_task({"assignee": "Asha", "task": "Send the report", "deadline": "2026-13-45"})
    assert ok and parsed.deadline == "TBD"


def test_relative_deadline_is_kept():
    ok, parsed, _ = validate_single_task({"assignee": "Asha", "task": "Send the report", "deadline": "by Friday"})
    assert ok and parsed.deadline == "by Friday"


def test_batch_keeps_only_valid_tasks():
    raw = [
        {"assignee": "John", "task": "Review the PR", "confidence": 0.95},
        {"assignee": "", "task": "Bad task"},
        "not a dict",
        {"assignee": "Sarah", "task": "Write the docs", "confidence": 0.8},
    ]
    valid = validate_and_parse_tasks(raw, job_id="t")
    assert [t.assignee for t in valid] == ["John", "Sarah"]


def test_empty_input_returns_empty_list():
    assert validate_and_parse_tasks([], "t") == []
