import json
import os
import sqlite3
from pathlib import Path
from typing import Any


DATA_PATH = Path(os.getenv("CAMPUS_DB_PATH", Path(__file__).resolve().parent.parent / "campus.db"))


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATA_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                title TEXT NOT NULL,
                code TEXT NOT NULL,
                day TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                room TEXT NOT NULL,
                instructor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                call_number TEXT NOT NULL,
                location TEXT NOT NULL,
                copies INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS landmarks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                aliases TEXT NOT NULL,
                building TEXT NOT NULL,
                details TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS campus_search USING fts5(kind, item_id UNINDEXED, content);
            CREATE TABLE IF NOT EXISTS preferences (
                student_id TEXT PRIMARY KEY,
                data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                remind_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY,
                intent TEXT NOT NULL,
                success INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
            _seed(db)
        book = db.execute("SELECT id FROM books WHERE title=?", ("Introduction to Computer Science",)).fetchone()
        if not book:
            cursor = db.execute(
                "INSERT INTO books(title,author,call_number,location,copies) VALUES(?,?,?,?,?)",
                ("Introduction to Computer Science", "Charles R. Severance", "QA 76.6 .S47", "Main Library · Level 3 · Shelf C08", 4),
            )
            db.execute(
                "INSERT INTO campus_search(kind,item_id,content) VALUES('book',?,?)",
                (cursor.lastrowid, "Introduction to Computer Science Charles R. Severance"),
            )


def _seed(db: sqlite3.Connection) -> None:
    courses = [
        ("student-001", "Introduction to Computer Science", "CS 101", "Monday", "09:00", "10:15", "North Hall 204", "Dr. Maya Chen"),
        ("student-001", "Data Structures", "CS 210", "Monday", "13:00", "14:15", "Innovation Center 310", "Prof. Eli Brooks"),
        ("student-001", "Calculus II", "MATH 202", "Tuesday", "10:30", "11:45", "West Hall 118", "Dr. Priya Shah"),
        ("student-001", "Human-Computer Interaction", "CS 340", "Wednesday", "11:00", "12:15", "Design Studio 12", "Prof. Jordan Lee"),
        ("student-001", "Introduction to Computer Science", "CS 101", "Thursday", "09:00", "10:15", "North Hall 204", "Dr. Maya Chen"),
        ("student-001", "Data Structures", "CS 210", "Friday", "13:00", "14:15", "Innovation Center 310", "Prof. Eli Brooks"),
    ]
    db.executemany(
        "INSERT INTO courses(student_id,title,code,day,start_time,end_time,room,instructor) VALUES(?,?,?,?,?,?,?,?)",
        courses,
    )
    books = [
        ("Introduction to Algorithms", "Thomas H. Cormen et al.", "QA 76.6 .C662", "Science Library · Level 3 · Shelf C12", 3),
        ("Introduction to Computer Science", "Charles R. Severance", "QA 76.6 .S47", "Main Library · Level 3 · Shelf C08", 4),
        ("Designing with the Mind in Mind", "Jeff Johnson", "QA 76.9 .H85 J64", "Design Library · Level 1 · Shelf D04", 2),
        ("A Brief History of Time", "Stephen Hawking", "QB 981 .H39", "Science Library · Level 2 · Shelf B08", 1),
        ("The Pragmatic Programmer", "David Thomas and Andrew Hunt", "QA 76.6 .T463", "Main Library · Level 2 · Shelf A17", 0),
    ]
    db.executemany("INSERT INTO books(title,author,call_number,location,copies) VALUES(?,?,?,?,?)", books)
    landmarks = [
        ("North Hall", "north hall|north building|cs building", "North campus", "Computer Science classrooms; accessible entrance faces the quad."),
        ("Science Library", "science library|library|main library", "Central campus", "Open today 8:00 AM–10:00 PM. Main entrance is on Library Walk."),
        ("Innovation Center", "innovation center|innovation|ic", "East campus", "Engineering and computing labs; accessible entrance on Founders Way."),
        ("West Hall", "west hall|math building", "West campus", "Mathematics classrooms; use the south entrance for step-free access."),
        ("Student Center", "student center|union|campus center", "Central campus", "Dining, student services, and the central information desk."),
        ("Design Studio", "design studio|design building", "Arts district", "Studios and seminar rooms; entrance is beside the sculpture garden."),
    ]
    db.executemany("INSERT INTO landmarks(name,aliases,building,details) VALUES(?,?,?,?)", landmarks)
    for row in db.execute("SELECT id,title,author FROM books"):
        db.execute("INSERT INTO campus_search(kind,item_id,content) VALUES('book',?,?)", (row["id"], f"{row['title']} {row['author']}"))
    for row in db.execute("SELECT id,title,code FROM courses"):
        db.execute("INSERT INTO campus_search(kind,item_id,content) VALUES('course',?,?)", (row["id"], f"{row['title']} {row['code']}"))
    for row in db.execute("SELECT id,name,aliases,building FROM landmarks"):
        db.execute("INSERT INTO campus_search(kind,item_id,content) VALUES('place',?,?)", (row["id"], f"{row['name']} {row['aliases']} {row['building']}"))
    db.execute("INSERT OR IGNORE INTO preferences(student_id,data) VALUES('student-001',?)", (json.dumps({"home_location": "Student Center", "reminder_minutes": 10}),))


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]