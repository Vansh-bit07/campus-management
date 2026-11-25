from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, Field


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "events.db"))


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'attendee'
                    CHECK (role IN ('attendee', 'organizer'))
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                organizer_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK (capacity > 0),
                status TEXT NOT NULL DEFAULT 'published'
                    CHECK (status IN ('draft', 'published', 'cancelled'))
            );

            CREATE TABLE IF NOT EXISTS registrations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                event_id TEXT NOT NULL REFERENCES events(id),
                created_at TEXT NOT NULL,
                UNIQUE (user_id, event_id)
            );

            CREATE INDEX IF NOT EXISTS registrations_user_id_idx
                ON registrations(user_id);
            CREATE INDEX IF NOT EXISTS registrations_event_id_idx
                ON registrations(event_id);
            """
        )

        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            organizer_id = str(uuid4())
            attendee_id = str(uuid4())
            connection.executemany(
                "INSERT INTO users (id, email, role) VALUES (?, ?, ?)",
                [
                    (organizer_id, "organizer@example.com", "organizer"),
                    (attendee_id, "attendee@example.com", "attendee"),
                ],
            )
            connection.execute(
                "INSERT INTO events (id, organizer_id, title, capacity, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), organizer_id, "Community meetup", 50, "published"),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Events API",
    version="1.0.0",
    description="Event browsing and registration API. Authentication is intentionally disabled for now.",
    lifespan=lifespan,
)


class EventResponse(BaseModel):
    id: UUID
    organizer_id: UUID
    title: str
    capacity: int
    status: str
    registration_count: int = 0


class RegistrationCreate(BaseModel):
    event_id: UUID
    user_id: UUID = Field(description="Temporary user identity until authentication is added")


class RegistrationResponse(BaseModel):
    id: UUID
    user_id: UUID
    event_id: UUID
    created_at: datetime


def row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def row_to_registration(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["created_at"] = datetime.fromisoformat(result["created_at"])
    return result


def parse_user_id(value: str | None) -> str:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a user id using the X-User-Id header.",
        )
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.") from exc


@app.get("/api/events", response_model=list[EventResponse])
def list_events(
    event_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = """
        SELECT e.*, COUNT(r.id) AS registration_count
        FROM events e
        LEFT JOIN registrations r ON r.event_id = e.id
    """
    parameters: list[Any] = []
    if event_status:
        query += " WHERE e.status = ?"
        parameters.append(event_status)
    query += " GROUP BY e.id ORDER BY e.title LIMIT ? OFFSET ?"
    parameters.extend([limit, offset])
    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [row_to_event(row) for row in rows]


@app.get("/api/events/{event_id}", response_model=EventResponse)
def get_event(event_id: UUID):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT e.*, COUNT(r.id) AS registration_count
            FROM events e
            LEFT JOIN registrations r ON r.event_id = e.id
            WHERE e.id = ?
            GROUP BY e.id
            """,
            (str(event_id),),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return row_to_event(row)


@app.post("/api/registrations", response_model=RegistrationResponse, status_code=201)
def create_registration(payload: RegistrationCreate):
    registration_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        user = connection.execute("SELECT id FROM users WHERE id = ?", (str(payload.user_id),)).fetchone()
        event = connection.execute(
            "SELECT id, capacity, status FROM events WHERE id = ?", (str(payload.event_id),)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        if event["status"] != "published":
            raise HTTPException(status_code=409, detail="Registrations are closed for this event.")
        existing = connection.execute(
            "SELECT id FROM registrations WHERE user_id = ? AND event_id = ?",
            (str(payload.user_id), str(payload.event_id)),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="User is already registered for this event.")
        registered = connection.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ?", (str(payload.event_id),)
        ).fetchone()[0]
        if registered >= event["capacity"]:
            raise HTTPException(status_code=409, detail="Event capacity has been reached.")
        connection.execute(
            "INSERT INTO registrations (id, user_id, event_id, created_at) VALUES (?, ?, ?, ?)",
            (registration_id, str(payload.user_id), str(payload.event_id), created_at),
        )
    return {"id": registration_id, "user_id": payload.user_id, "event_id": payload.event_id, "created_at": created_at}


@app.get("/api/me/registrations", response_model=list[RegistrationResponse])
def list_my_registrations(x_user_id: str | None = Header(default=None)):
    user_id = parse_user_id(x_user_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM registrations WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [row_to_registration(row) for row in rows]


@app.get("/api/events/{event_id}/registrations", response_model=list[RegistrationResponse])
def list_event_registrations(event_id: UUID, x_user_id: str | None = Header(default=None)):
    user_id = parse_user_id(x_user_id)
    with get_connection() as connection:
        event = connection.execute(
            "SELECT organizer_id FROM events WHERE id = ?", (str(event_id),)
        ).fetchone()
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        if event["organizer_id"] != user_id:
            raise HTTPException(status_code=403, detail="Only the event organizer can view attendees.")
        rows = connection.execute(
            "SELECT * FROM registrations WHERE event_id = ? ORDER BY created_at ASC", (str(event_id),)
        ).fetchall()
    return [row_to_registration(row) for row in rows]


@app.get("/health")
def health_check():
    return {"status": "ok"}
