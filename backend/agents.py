import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

import httpx
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from backend.database import connect, rows_as_dicts

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class CampusState(TypedDict, total=False):
    student_id: str
    query: str
    context: str
    intent: str
    entities: dict[str, str]
    records: list[dict[str, Any]]
    answer: str
    error: str
    reflected: bool


def _groq_completion(messages: list[dict[str, str]], temperature: float = 0.2) -> str | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), "messages": messages, "temperature": temperature},
            timeout=12,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None


def query_parser(state: CampusState) -> dict[str, Any]:
    query = state["query"].strip()
    if state.get("context") == "library":
        return {"intent": "library", "entities": {}}
    llm_result = _groq_completion([
        {"role": "system", "content": 'Classify a campus query. Return JSON only: {"intent":"schedule|library|navigation|unclear","entities":{}}. Use navigation for directions/location, library for books/loans, schedule for classes.'},
        {"role": "user", "content": query},
    ])
    if llm_result:
        try:
            parsed = json.loads(re.search(r"\{.*\}", llm_result, re.DOTALL).group(0))
            if parsed.get("intent") in {"schedule", "library", "navigation", "unclear"}:
                return {"intent": parsed["intent"], "entities": parsed.get("entities", {})}
        except (AttributeError, json.JSONDecodeError, TypeError):
            pass

    text = query.lower()
    if any(word in text for word in ("book", "library", "reserve", "borrow", "loan", "return", "author", "catalog")):
        intent = "library"
    elif any(word in text for word in ("where", "direction", "navigate", "find", "location", "building", "room")) and not any(word in text for word in ("class", "schedule", "timetable", "next lecture")):
        intent = "navigation"
    elif any(word in text for word in ("class", "schedule", "timetable", "lecture", "course", "next class", "reminder")):
        intent = "schedule"
    else:
        intent = "unclear"
    return {"intent": intent, "entities": {}}


def _search(query: str, kind: str) -> list[dict[str, Any]]:
    stop_words = {"a", "an", "and", "book", "building", "campus", "do", "find", "for", "get", "how", "i", "is", "me", "my", "of", "on", "the", "to", "where"}
    terms = [term for term in re.findall(r"[\w]+", query.lower()) if term not in stop_words]
    with connect() as db:
        if terms:
            match = " OR ".join(f'"{term}"*' for term in terms[:8])
            try:
                hits = db.execute("SELECT item_id FROM campus_search WHERE kind=? AND campus_search MATCH ? ORDER BY rank LIMIT 5", (kind, match)).fetchall()
            except Exception:
                hits = []
            if hits:
                ids = [int(hit[0]) for hit in hits]
            else:
                ids = []
        else:
            ids = []
        table = {"book": "books", "course": "courses", "place": "landmarks"}[kind]
        if not ids:
            rows = db.execute(f"SELECT * FROM {table} LIMIT 0").fetchall()
            return rows_as_dicts(rows)
        placeholders = ",".join("?" for _ in ids)
        order = "CASE id " + " ".join(f"WHEN {item_id} THEN {index}" for index, item_id in enumerate(ids)) + " END"
        return rows_as_dicts(db.execute(f"SELECT * FROM {table} WHERE id IN ({placeholders}) ORDER BY {order}", ids).fetchall())


def _schedule_agent(state: CampusState) -> dict[str, Any]:
    now = datetime.now().astimezone()
    with connect() as db:
        all_classes = rows_as_dicts(db.execute("SELECT * FROM courses WHERE student_id=?", (state["student_id"],)).fetchall())
    upcoming = []
    for item in all_classes:
        weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(item["day"])
        days_ahead = (weekday - now.weekday()) % 7
        start = datetime.combine((now + timedelta(days=days_ahead)).date(), datetime.strptime(item["start_time"], "%H:%M").time()).astimezone()
        if start <= now:
            start += timedelta(days=7)
        item["starts_at"] = start.isoformat()
        upcoming.append(item)
    upcoming.sort(key=lambda item: item["starts_at"])
    if "reminder" in state["query"].lower() and upcoming:
        with connect() as db:
            preference_row = db.execute("SELECT data FROM preferences WHERE student_id=?", (state["student_id"],)).fetchone()
            preferences = json.loads(preference_row["data"]) if preference_row else {}
            match = re.search(r"(\d+)\s*minutes?", state["query"].lower())
            minutes = int(match.group(1)) if match else int(preferences.get("reminder_minutes", 10))
            remind_at = datetime.fromisoformat(upcoming[0]["starts_at"]) - timedelta(minutes=minutes)
            db.execute("INSERT INTO reminders(student_id,course_id,remind_at) VALUES(?,?,?)", (state["student_id"], upcoming[0]["id"], remind_at.isoformat()))
        return {"records": [upcoming[0]], "answer": f"Reminder set for {upcoming[0]['title']} {minutes} minutes before class."}
    if "all" in state["query"].lower() or "week" in state["query"].lower() or "schedule" in state["query"].lower() or "timetable" in state["query"].lower():
        chosen = upcoming[:6]
        answer = "Here’s your upcoming class schedule."
    else:
        chosen = upcoming[:1]
        answer = "Your next class is coming up."
    return {"records": chosen, "answer": answer}


def _library_agent(state: CampusState) -> dict[str, Any]:
    books = _search(state["query"], "book")
    text = state["query"].lower()
    if any(word in text for word in ("reserve", "hold")):
        if books:
            with connect() as db:
                db.execute("INSERT INTO approvals(student_id,kind,details) VALUES(?,?,?)", (state["student_id"], "book_reservation", json.dumps({"book_id": books[0]["id"], "title": books[0]["title"]})))
            return {"records": books[:1], "answer": "I found the book. A staff member needs to approve the reservation before it is placed."}
    if any(word in text for word in ("extend", "renew")):
        with connect() as db:
            db.execute("INSERT INTO approvals(student_id,kind,details) VALUES(?,?,?)", (state["student_id"], "loan_extension", json.dumps({"request": state["query"]})))
        return {"records": books[:1], "answer": "I’ve sent the loan extension request to the library team for review."}
    if not books:
        return {"records": [], "answer": "I couldn’t find a close catalog match. Try a title, author, or a few keywords."}
    return {"records": books[:5], "answer": "Here are the closest matches from the campus catalog."}


def _navigation_agent(state: CampusState) -> dict[str, Any]:
    places = _search(state["query"], "place")
    if not places:
        return {"records": [], "answer": "I couldn’t match that place to the campus directory. Try a building name or campus facility."}
    place = places[0]
    with connect() as db:
        row = db.execute("SELECT data FROM preferences WHERE student_id=?", (state["student_id"],)).fetchone()
    origin = json.loads(row["data"]).get("home_location", "Student Center") if row else "Student Center"
    place["route"] = f"From {origin}, follow campus wayfinding signs to {place['name']}. Check the accessible entrance note before setting out."
    return {"records": [place], "answer": f"{place['name']} is in {place['building']}. Here’s the campus route."}


def _error_agent(_state: CampusState) -> dict[str, Any]:
    return {"records": [], "answer": "I can help with your class schedule, campus library, or directions. What are you looking for?", "error": f"intent_unclear: {_state['query']}"}


def _response_generator(state: CampusState) -> dict[str, Any]:
    if state.get("error"):
        return {"reflected": True}
    if not state.get("records"):
        return {"reflected": state["intent"] == "library" and "couldn’t find" in state.get("answer", "") or state["intent"] == "navigation" and "couldn’t match" in state.get("answer", "")}
    generated = _groq_completion([
        {"role": "system", "content": f"Answer the student using only these retrieved records. Intent: {state['intent']}. Be concise, do not invent availability, opening hours, or real map turn-by-turn directions."},
        {"role": "user", "content": f"Question: {state['query']}\nRecords: {json.dumps(state['records'])}\nDraft: {state.get('answer', '')}"},
    ], 0.3)
    answer = generated.strip() if generated else state.get("answer", "")
    valid = bool(answer) and state["intent"] in {"schedule", "library", "navigation"}
    return {"answer": answer if valid else "I couldn’t verify a result for that request. Please try rephrasing it.", "reflected": valid}


def _analytics_agent(state: CampusState) -> dict[str, Any]:
    with connect() as db:
        db.execute("INSERT INTO analytics(intent,success) VALUES(?,?)", (state.get("intent", "unclear"), int(bool(state.get("reflected")))))
    return {}


def _route(state: CampusState) -> str:
    return {"schedule": "schedule", "library": "library", "navigation": "navigation"}.get(state["intent"], "error")


def _build_graph():
    graph = StateGraph(CampusState)
    graph.add_node("query_parser", query_parser)
    graph.add_node("schedule", _schedule_agent)
    graph.add_node("library", _library_agent)
    graph.add_node("navigation", _navigation_agent)
    graph.add_node("error", _error_agent)
    graph.add_node("response_generator", _response_generator)
    graph.add_node("analytics", _analytics_agent)
    graph.add_edge(START, "query_parser")
    graph.add_conditional_edges("query_parser", _route, {"schedule": "schedule", "library": "library", "navigation": "navigation", "error": "error"})
    for agent in ("schedule", "library", "navigation", "error"):
        graph.add_edge(agent, "response_generator")
    graph.add_edge("response_generator", "analytics")
    graph.add_edge("analytics", END)
    return graph.compile()


campus_graph = _build_graph()


def handle_query(student_id: str, query: str, context: str | None = None) -> CampusState:
    state: CampusState = {"student_id": student_id, "query": query}
    if context:
        state["context"] = context
    return campus_graph.invoke(state)