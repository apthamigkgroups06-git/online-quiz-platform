from datetime import UTC, datetime
from typing import Annotated

import psycopg
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from . import cache, db
from .scoring import QuizError, deadline_for, grade, is_expired, seconds_left

app = FastAPI(title="online-quiz")


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}

    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except psycopg.Error:
        out["pg_error"] = "PostgreSQL connection failed"

    try:
        cache.client().ping()
        out["redis"] = True
    except RedisError:
        out["redis_error"] = "Redis connection failed"

    return (
        out
        if out["postgres"] and out["redis"]
        else JSONResponse(out, status_code=503)
    )


@app.get("/quizzes")
def quizzes():
    return {
        "quizzes": db.query(
            "SELECT q.id, q.title, q.limit_seconds, q.negative_marks,"
            " (SELECT count(*) FROM questions x WHERE x.quiz_id=q.id) AS questions"
            " FROM quizzes q ORDER BY q.id"
        )
    }


@app.post("/attempts", status_code=201)
def start(payload: Annotated[dict, Body()]):
    quiz = db.one(
        "SELECT id, limit_seconds FROM quizzes WHERE id=%s",
        (payload.get("quiz_id"),),
    )

    if not quiz:
        raise HTTPException(404, "no such quiz")

    student = str(payload.get("student", "")).strip()

    if not student:
        raise HTTPException(400, "student is required")

    now = datetime.now(UTC)

    try:
        deadline = deadline_for(now, quiz["limit_seconds"])
    except QuizError as exc:
        raise HTTPException(400, str(exc)) from exc

    row = db.one(
        "INSERT INTO attempts (quiz_id, student, deadline) "
        "VALUES (%s,%s,%s) RETURNING id",
        (quiz["id"], student, deadline),
    )

    cache.set_json(
        f"attempt:{row['id']}",
        {"answers": {}, "deadline": deadline.isoformat()},
        ttl=quiz["limit_seconds"] + 120,
    )

    return {
        "attempt_id": row["id"],
        "seconds_left": seconds_left(deadline, now),
    }


def _attempt(aid):
    attempt = db.one(
        "SELECT id, quiz_id, student, deadline, submitted "
        "FROM attempts WHERE id=%s",
        (aid,),
    )

    if not attempt:
        raise HTTPException(404, "no such attempt")

    return attempt


@app.get("/attempts/{aid}")
def progress(aid: int):
    attempt = _attempt(aid)
    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}

    return {
        "attempt_id": aid,
        "student": attempt["student"],
        "submitted": attempt["submitted"],
        "seconds_left": seconds_left(attempt["deadline"]),
        "answered": len(live.get("answers", {})),
    }


@app.post("/attempts/{aid}/answer")
def answer(aid: int, payload: Annotated[dict, Body()]):
    attempt = _attempt(aid)

    if attempt["submitted"]:
        raise HTTPException(409, "this attempt is already submitted")

    if is_expired(attempt["deadline"]):
        raise HTTPException(409, "time is up")

    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}
    question_id = str(payload.get("question_id"))
    live.setdefault("answers", {})[question_id] = payload.get("choice", [])

    cache.set_json(
        f"attempt:{aid}",
        live,
        ttl=max(60, seconds_left(attempt["deadline"]) + 120),
    )

    return {
        "saved": True,
        "question_id": question_id,
        "seconds_left": seconds_left(attempt["deadline"]),
    }


@app.post("/attempts/{aid}/submit")
def submit(aid: int):
    attempt = _attempt(aid)

    if attempt["submitted"]:
        raise HTTPException(409, "already submitted")

    quiz = db.one(
        "SELECT negative_marks, partial_credit FROM quizzes WHERE id=%s",
        (attempt["quiz_id"],),
    )

    questions = db.query(
        "SELECT id, marks, correct FROM questions "
        "WHERE quiz_id=%s ORDER BY id",
        (attempt["quiz_id"],),
    )

    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}
    answers = {
        int(key): value for key, value in live.get("answers", {}).items()
    }

    result = grade(
        [
            {
                "id": question["id"],
                "marks": question["marks"],
                "correct": question["correct"],
            }
            for question in questions
        ],
        answers,
        float(quiz["negative_marks"]),
        quiz["partial_credit"],
    )

    db.query(
        "UPDATE attempts SET submitted=TRUE, score=%s WHERE id=%s",
        (result["score"], aid),
        fetch=False,
    )

    cache.drop(f"attempt:{aid}")

    return {
        "attempt_id": aid,
        "late": is_expired(attempt["deadline"]),
        **result,
    }