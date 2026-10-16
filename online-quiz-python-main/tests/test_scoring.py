from datetime import datetime, timedelta, timezone

import pytest

from app.scoring import (
    QuizError,
    deadline_for,
    seconds_left,
    is_expired,
    score_question,
    grade,
)


# Tests for deadline_for()

def test_deadline_for_returns_correct_deadline():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = deadline_for(start, 60)
    assert result == start + timedelta(seconds=60)


def test_deadline_for_rejects_zero_time_limit():
    start = datetime.now(timezone.utc)
    with pytest.raises(QuizError):
        deadline_for(start, 0)


def test_deadline_for_rejects_negative_time_limit():
    start = datetime.now(timezone.utc)
    with pytest.raises(QuizError):
        deadline_for(start, -10)


# Tests for seconds_left()

def test_seconds_left_returns_remaining_seconds():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now + timedelta(seconds=60)
    assert seconds_left(deadline, now) == 60


def test_seconds_left_returns_zero_after_deadline():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now - timedelta(seconds=10)
    assert seconds_left(deadline, now) == 0


def test_seconds_left_rounds_down_to_integer():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now + timedelta(seconds=5.9)
    assert seconds_left(deadline, now) == 5


# Tests for is_expired()

def test_is_expired_after_grace_period():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now - timedelta(seconds=5)
    assert is_expired(deadline, now) is True


def test_is_not_expired_within_grace_period():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now - timedelta(seconds=1)
    assert is_expired(deadline, now) is False


def test_is_expired_respects_custom_grace_period():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deadline = now - timedelta(seconds=10)
    assert is_expired(deadline, now, grace_seconds=5) is True


# Tests for score_question()

def test_correct_answer_gets_full_marks():
    assert score_question({1, 2}, {1, 2}) == 1.0


def test_wrong_answer_gets_zero_without_negative_marking():
    assert score_question({1}, {2}) == 0.0


def test_unanswered_question_gets_zero():
    assert score_question({1}, set()) == 0.0


def test_wrong_answer_applies_negative_marking():
    assert score_question({1}, {2}, negative=0.5) == -0.5


def test_partial_marks_for_partially_correct_answer():
    assert score_question(
        {1, 2}, {1}, marks=2.0, partial=True
    ) == 1.0


def test_partial_marking_with_wrong_choice_applies_penalty():
    assert score_question(
        {1, 2}, {1, 3}, marks=2.0, negative=0.5, partial=True
    ) == -0.5


def test_correct_answer_respects_custom_marks():
    assert score_question({1}, {1}, marks=5.0) == 5.0


# Tests for grade()

def test_grade_returns_correct_total_and_percentage():
    questions = [
        {"id": 1, "correct": [1], "marks": 2},
        {"id": 2, "correct": [2], "marks": 2},
    ]
    answers = {1: [1], 2: [3]}

    result = grade(questions, answers)

    assert result["score"] == 2.0
    assert result["possible"] == 4.0
    assert result["percent"] == 50.0


def test_grade_never_returns_negative_total():
    questions = [
        {"id": 1, "correct": [1], "marks": 1},
]
    answers = {1: [2]}

    result = grade(questions, answers)

    assert result["score"] >= 0
   