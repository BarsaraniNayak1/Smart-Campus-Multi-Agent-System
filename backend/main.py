import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.agents import handle_query
from backend.database import connect, init_db, rows_as_dicts


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    app.state.database_ready = True
    yield
    app.state.database_ready = False


app = FastAPI(title="Smart Campus Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    student_id: str = "student-001"
    context: Literal["library"] | None = None


class PreferenceUpdate(BaseModel):
    home_location: str = Field(min_length=1, max_length=100)
    reminder_minutes: int = Field(default=10, ge=0, le=120)


@app.get("/api/health")
def health(request: Request) -> dict[str, str]:
    status = "ok" if getattr(request.app.state, "database_ready", False) else "starting"
    return {"status": status, "service": "smart-campus-assistant"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    student_id = request.student_id.strip()
    query = request.message.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Message cannot be blank")
    try:
        result = handle_query(student_id, query, request.context)
    except Exception as exc:
        with connect() as db:
            db.execute("INSERT INTO analytics(intent,success) VALUES('error',0)")
        raise HTTPException(status_code=503, detail="Campus services are temporarily unavailable") from exc
    with connect() as db:
        db.execute("INSERT INTO messages(student_id,role,content,intent) VALUES(?,?,?,?)", (student_id, "user", query, result.get("intent")))
        db.execute("INSERT INTO messages(student_id,role,content,intent) VALUES(?,?,?,?)", (student_id, "assistant", result.get("answer", ""), result.get("intent")))
    return {"answer": result.get("answer", ""), "intent": result.get("intent", "unclear"), "records": result.get("records", []), "reflected": result.get("reflected", False)}


@app.get("/api/schedule")
def schedule(student_id: str = "student-001") -> dict[str, Any]:
    with connect() as db:
        courses = rows_as_dicts(db.execute("SELECT * FROM courses WHERE student_id=? ORDER BY CASE day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END,start_time", (student_id,)).fetchall())
    return {"courses": courses}


@app.get("/api/history")
def history(student_id: str = "student-001", limit: int = 40) -> dict[str, Any]:
    with connect() as db:
        messages = rows_as_dicts(db.execute("SELECT id,role,content,intent,created_at FROM messages WHERE student_id=? ORDER BY id DESC LIMIT ?", (student_id, min(max(limit, 1), 100))).fetchall())
    return {"messages": list(reversed(messages))}


@app.get("/api/preferences")
def get_preferences(student_id: str = "student-001") -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT data FROM preferences WHERE student_id=?", (student_id,)).fetchone()
    return json.loads(row["data"]) if row else {"home_location": "Student Center", "reminder_minutes": 10}


@app.put("/api/preferences")
def update_preferences(preferences: PreferenceUpdate, student_id: str = "student-001") -> dict[str, Any]:
    data = preferences.model_dump()
    with connect() as db:
        db.execute("INSERT INTO preferences(student_id,data) VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET data=excluded.data", (student_id, json.dumps(data)))
    return data


@app.get("/api/approvals")
def approvals() -> dict[str, Any]:
    with connect() as db:
        items = rows_as_dicts(db.execute("SELECT * FROM approvals ORDER BY id DESC").fetchall())
    for item in items:
        item["details"] = json.loads(item["details"])
    return {"approvals": items}


@app.patch("/api/approvals/{approval_id}")
def resolve_approval(approval_id: int, status: str) -> dict[str, Any]:
    if status not in {"approved", "declined"}:
        raise HTTPException(status_code=422, detail="Status must be approved or declined")
    with connect() as db:
        cursor = db.execute("UPDATE approvals SET status=? WHERE id=? AND status='pending'", (status, approval_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pending approval not found")
    return {"id": approval_id, "status": status}


@app.get("/api/analytics")
def analytics() -> dict[str, Any]:
    with connect() as db:
        totals = rows_as_dicts(db.execute("SELECT intent,COUNT(*) AS requests,SUM(success) AS successful FROM analytics GROUP BY intent ORDER BY requests DESC").fetchall())
        pending = db.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
    return {"by_intent": totals, "pending_approvals": pending}