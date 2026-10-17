from datetime import datetime, timezone

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import cache, db
from .scoring import QuizError, deadline_for, grade, is_expired, seconds_left

app = FastAPI(title="online-quiz")


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


@app.get("/quizzes")
def quizzes():
    return {"quizzes": db.query(
        "SELECT q.id, q.title, q.limit_seconds, q.negative_marks,"
        " (SELECT count(*) FROM questions x WHERE x.quiz_id=q.id) AS questions"
        " FROM quizzes q ORDER BY q.id")}


@app.post("/attempts", status_code=201)
def start(payload: dict = Body(...)):
    quiz = db.one("SELECT id, limit_seconds FROM quizzes WHERE id=%s",
                  (payload.get("quiz_id"),))
    if not quiz:
        raise HTTPException(404, "no such quiz")
    student = str(payload.get("student", "")).strip()
    if not student:
        raise HTTPException(400, "student is required")

    now = datetime.now(timezone.utc)
    try:
        dl = deadline_for(now, quiz["limit_seconds"])
    except QuizError as e:
        raise HTTPException(400, str(e))

    row = db.one("INSERT INTO attempts (quiz_id, student, deadline) VALUES (%s,%s,%s)"
                 " RETURNING id", (quiz["id"], student, dl))
    cache.set_json(f"attempt:{row['id']}", {"answers": {}, "deadline": dl.isoformat()},
                   ttl=quiz["limit_seconds"] + 120)
    return {"attempt_id": row["id"], "seconds_left": seconds_left(dl, now)}


def _attempt(aid):
    a = db.one("SELECT id, quiz_id, student, deadline, submitted FROM attempts WHERE id=%s",
               (aid,))
    if not a:
        raise HTTPException(404, "no such attempt")
    return a


@app.get("/attempts/{aid}")
def progress(aid: int):
    a = _attempt(aid)
    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}
    return {"attempt_id": aid, "student": a["student"], "submitted": a["submitted"],
            "seconds_left": seconds_left(a["deadline"]),
            "answered": len(live.get("answers", {}))}


@app.post("/attempts/{aid}/answer")
def answer(aid: int, payload: dict = Body(...)):
    a = _attempt(aid)
    if a["submitted"]:
        raise HTTPException(409, "this attempt is already submitted")
    if is_expired(a["deadline"]):
        raise HTTPException(409, "time is up")
    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}
    qid = str(payload.get("question_id"))
    live.setdefault("answers", {})[qid] = payload.get("choice", [])
    cache.set_json(f"attempt:{aid}", live, ttl=max(60, seconds_left(a["deadline"]) + 120))
    return {"saved": True, "question_id": qid, "seconds_left": seconds_left(a["deadline"])}


@app.post("/attempts/{aid}/submit")
def submit(aid: int):
    a = _attempt(aid)
    if a["submitted"]:
        raise HTTPException(409, "already submitted")
    quiz = db.one("SELECT negative_marks, partial_credit FROM quizzes WHERE id=%s",
                  (a["quiz_id"],))
    qs = db.query("SELECT id, marks, correct FROM questions WHERE quiz_id=%s ORDER BY id",
                  (a["quiz_id"],))
    live = cache.get_json(f"attempt:{aid}") or {"answers": {}}
    answers = {int(k): v for k, v in live.get("answers", {}).items()}
    result = grade([{"id": q["id"], "marks": q["marks"], "correct": q["correct"]} for q in qs],
                   answers, float(quiz["negative_marks"]), quiz["partial_credit"])
    db.query("UPDATE attempts SET submitted=TRUE, score=%s WHERE id=%s",
             (result["score"], aid), fetch=False)
    cache.drop(f"attempt:{aid}")
    return {"attempt_id": aid, "late": is_expired(a["deadline"]), **result}
