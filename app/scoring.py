"""Pure scoring and timing rules. No database, no HTTP."""
from datetime import datetime, timedelta, timezone


class QuizError(ValueError):
    pass


def deadline_for(started_at, limit_seconds):
    """When this attempt must be finished.

    Storing the DEADLINE rather than 'seconds remaining' is the whole trick:
    a deadline survives a page refresh, a server restart and a closed laptop.
    """
    if limit_seconds <= 0:
        raise QuizError("the time limit must be positive")
    return started_at + timedelta(seconds=limit_seconds)


def seconds_left(deadline, now=None):
    now = now or datetime.now(timezone.utc)
    return max(0, int((deadline - now).total_seconds()))


def is_expired(deadline, now=None, grace_seconds=2):
    """Grace allows for the round trip between the student's click and the server."""
    now = now or datetime.now(timezone.utc)
    return (now - deadline).total_seconds() > grace_seconds


def score_question(correct, given, marks=1.0, negative=0.0, partial=False):
    """Score one question.

    correct / given are sets of choice ids.
      negative : marks deducted for a wrong answer (0 for no negative marking)
      partial  : award a fraction for getting some of a multi-answer right
    An unanswered question always scores zero - never a penalty.
    """
    correct, given = set(correct), set(given)
    if not given:
        return 0.0
    if given == correct:
        return float(marks)
    if partial and len(correct) > 1:
        right = len(given & correct)
        wrong = len(given - correct)
        if wrong:
            return -float(negative)
        return round(marks * right / len(correct), 3)
    return -float(negative)


def grade(questions, answers, negative=0.0, partial=False):
    """Score a whole attempt.

    questions: [{"id":1,"correct":[2],"marks":1}]
    answers  : {question_id: [choice ids]}
    """
    total = 0.0
    possible = 0.0
    breakdown = []
    for q in questions:
        marks = float(q.get("marks", 1))
        possible += marks
        got = score_question(q["correct"], answers.get(q["id"], []), marks, negative, partial)
        total += got
        breakdown.append({"question_id": q["id"], "awarded": got, "out_of": marks,
                          "answered": bool(answers.get(q["id"]))})
    total = max(0.0, total)      # a quiz never scores below zero
    pct = round(100 * total / possible, 1) if possible else 0.0
    return {"score": round(total, 2), "possible": round(possible, 2),
            "percent": pct, "breakdown": breakdown}
