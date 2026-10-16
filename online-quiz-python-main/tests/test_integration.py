from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_health_returns_ok_when_services_are_available(monkeypatch):
    monkeypatch.setattr(main.db, "query", lambda *args, **kwargs: [1])
    monkeypatch.setattr(main.cache, "client", lambda: type(
        "FakeRedis", (), {"ping": lambda self: True}
    )())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is True


def test_list_quizzes(monkeypatch):
    expected = [
        {
            "id": 1,
            "title": "Sample Quiz",
            "limit_seconds": 300,
            "negative_marks": 0,
            "questions": 2,
        }
    ]

    monkeypatch.setattr(main.db, "query", lambda *args, **kwargs: expected)

    response = client.get("/quizzes")

    assert response.status_code == 200
    assert response.json()["quizzes"] == expected


def test_start_attempt_for_missing_quiz(monkeypatch):
    monkeypatch.setattr(main.db, "one", lambda *args, **kwargs: None)

    response = client.post(
        "/attempts",
        json={"quiz_id": 999, "student": "Student A"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "no such quiz"


def test_start_attempt_requires_student(monkeypatch):
    monkeypatch.setattr(
        main.db,
        "one",
        lambda *args, **kwargs: {"id": 1, "limit_seconds": 300},
    )

    response = client.post("/attempts", json={"quiz_id": 1, "student": " "})

    assert response.status_code == 400
    assert response.json()["detail"] == "student is required"


def test_start_attempt_success(monkeypatch):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=300)
    calls = []

    def fake_one(sql, params=None):
        if "SELECT id, limit_seconds" in sql:
            return {"id": 1, "limit_seconds": 300}
        if "INSERT INTO attempts" in sql:
            return {"id": 42}
        return None

    monkeypatch.setattr(main.db, "one", fake_one)
    monkeypatch.setattr(
        main.cache,
        "set_json",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(main, "deadline_for", lambda now, seconds: deadline)

    response = client.post(
        "/attempts",
        json={"quiz_id": 1, "student": "Student A"},
    )

    assert response.status_code == 201
    assert response.json()["attempt_id"] == 42
    assert response.json()["seconds_left"] > 0
    assert len(calls) == 1


def test_save_answer_success(monkeypatch):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=300)
    saved = {}

    monkeypatch.setattr(
        main,
        "_attempt",
        lambda aid: {
            "id": aid,
            "quiz_id": 1,
            "student": "Student A",
            "deadline": deadline,
            "submitted": False,
        },
    )
    monkeypatch.setattr(main, "is_expired", lambda value: False)
    monkeypatch.setattr(main, "seconds_left", lambda value: 200)
    monkeypatch.setattr(main.cache, "get_json", lambda key: {"answers": {}})
    monkeypatch.setattr(
        main.cache,
        "set_json",
        lambda key, value, ttl=300: saved.update(value),
    )

    response = client.post(
        "/attempts/42/answer",
        json={"question_id": 7, "choice": [2]},
    )

    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert saved["answers"]["7"] == [2]


def test_submit_attempt_success(monkeypatch):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=300)

    monkeypatch.setattr(
        main,
        "_attempt",
        lambda aid: {
            "id": aid,
            "quiz_id": 1,
            "student": "Student A",
            "deadline": deadline,
            "submitted": False,
        },
    )

    def fake_one(sql, params=None):
        if "SELECT negative_marks" in sql:
            return {"negative_marks": 0, "partial_credit": False}
        return None

    monkeypatch.setattr(main.db, "one", fake_one)
    monkeypatch.setattr(
        main.db,
        "query",
        lambda sql, params=None, fetch=True: (
            [{"id": 7, "marks": 1, "correct": [2]}]
            if "SELECT id, marks, correct" in sql
            else []
        ),
    )
    monkeypatch.setattr(
        main.cache,
        "get_json",
        lambda key: {"answers": {"7": [2]}},
    )
    monkeypatch.setattr(main.cache, "drop", lambda *args: None)
    monkeypatch.setattr(main, "is_expired", lambda value: False)

    response = client.post("/attempts/42/submit")

    assert response.status_code == 200
    assert response.json()["attempt_id"] == 42
    assert response.json()["score"] == 1