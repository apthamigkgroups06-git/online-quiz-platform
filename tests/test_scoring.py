from datetime import UTC, datetime, timedelta

import pytest

from app.scoring import (
    QuizError,
    deadline_for,
    grade,
    is_expired,
    score_question,
    seconds_left,
)

# Tests for deadline_for()

def test_deadline_for_valid_limit():
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    result = deadline_for(start, 60)

    assert result == start + timedelta(seconds=60)


def test_deadline_for_zero_limit():
    start = datetime.now(UTC)

    with pytest.raises(QuizError):
        deadline_for(start, 0)


def test_deadline_for_negative_limit():
    start = datetime.now(UTC)

    with pytest.raises(QuizError):
        deadline_for(start, -10)


# Tests for seconds_left()

def test_seconds_left_returns_remaining_time():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    deadline = now + timedelta(seconds=50)

    assert seconds_left(deadline, now) == 50


def test_seconds_left_returns_zero_after_deadline():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    deadline = now - timedelta(seconds=10)

    assert seconds_left(deadline, now) == 0


def test_seconds_left_rounds_down():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    deadline = now + timedelta(seconds=5.9)

    assert seconds_left(deadline, now) == 5


# Tests for is_expired()

def test_is_expired_before_deadline():
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    deadline = now + timedelta(seconds=10)

    assert is_expired(deadline, now) is False


def test_is_expired_within_grace_period():
    deadline = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    now = deadline + timedelta(seconds=1)

    assert is_expired(deadline, now) is False


def test_is_expired_after_grace_period():
    deadline = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    now = deadline + timedelta(seconds=3)

    assert is_expired(deadline, now) is True


# Tests for score_question()

def test_score_question_correct_answer():
    assert score_question([1], [1]) == 1.0


def test_score_question_wrong_answer_without_penalty():
    assert score_question([1], [2]) == 0.0


def test_score_question_wrong_answer_with_penalty():
    assert score_question([1], [2], negative=0.25) == -0.25


def test_score_question_unanswered():
    assert score_question([1], []) == 0.0


def test_score_question_custom_marks():
    assert score_question([1], [1], marks=5) == 5.0


def test_score_question_partial_credit():
    assert score_question(
        [1, 2, 3],
        [1, 2],
        marks=3,
        partial=True,
    ) == 2.0


def test_score_question_partial_credit_with_wrong_choice():
    assert score_question(
        [1, 2, 3],
        [1, 4],
        marks=3,
        negative=0.5,
        partial=True,
    ) == -0.5




def test_grade_all_correct():
    questions = [
        {"id": 1, "correct": [1], "marks": 2},
        {"id": 2, "correct": [3], "marks": 3},
    ]
    answers = {1: [1], 2: [3]}

    result = grade(questions, answers)

    assert result["score"] == 5.0
    assert result["possible"] == 5.0
    assert result["percent"] == 100.0


def test_grade_unanswered_question():
    questions = [{"id": 1, "correct": [1], "marks": 2}]

    result = grade(questions, {})

    assert result["score"] == 0.0
    assert result["breakdown"][0]["answered"] is False


def test_grade_score_never_below_zero():
    questions = [{"id": 1, "correct": [1], "marks": 1}]
    answers = {1: [2]}

    result = grade(questions, answers, negative=5)

    assert result["score"] == 0.0


def test_grade_empty_quiz():
    result = grade([], {})

    assert result["score"] == 0.0
    assert result["possible"] == 0.0
    assert result["percent"] == 0.0
    assert result["breakdown"] == []