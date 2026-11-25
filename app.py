from __future__ import annotations

import logging
import os
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from postgrest import APIError
from supabase import Client, create_client


load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)


def configured_cors_origins() -> str | list[str]:
    configured = os.getenv("CORS_ORIGINS", "*").strip()
    if configured == "*":
        return "*"
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


cors_origins = configured_cors_origins()
CORS(
    app,
    resources={
        r"/api/*": {"origins": cors_origins},
        r"/health": {"origins": cors_origins},
    },
)


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_PUBLISHABLE_KEY) must be configured."
        )
    return create_client(url, key)


def error_response(message: str, status_code: int):
    return jsonify({"detail": message}), status_code


def parse_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a valid UUID.")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID.") from exc


def parse_user_header() -> str:
    value = request.headers.get("X-User-Id")
    if not value:
        raise ValueError("Provide a user id using the X-User-Id header.")
    return parse_uuid(value, "X-User-Id")


def fetch_registration_counts(event_ids: list[str]) -> dict[str, int]:
    if not event_ids:
        return {}
    rows = (
        get_supabase()
        .table("registrations")
        .select("event_id")
        .in_("event_id", event_ids)
        .execute()
        .data
    )
    counts = {event_id: 0 for event_id in event_ids}
    for row in rows:
        event_id = str(row["event_id"])
        if event_id in counts:
            counts[event_id] = counts[event_id] + 1
    return counts


def add_registration_count(event: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    result = dict(event)
    result["registration_count"] = counts.get(str(event["id"]), 0)
    return result


@app.get("/")
def index():
    return jsonify({"name": "Events API", "docs": "/api/events", "health": "/health"})


@app.get("/app")
def frontend_redirect():
    return redirect("/app/", code=302)


@app.get("/app/")
def frontend_index():
    return send_from_directory(os.path.join(app.root_path, "frontend"), "index.html")


@app.get("/app/<path:filename>")
def frontend_asset(filename: str):
    return send_from_directory(os.path.join(app.root_path, "frontend"), filename)


@app.get("/api/events")
def list_events():
    event_status = request.args.get("status")
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return error_response("limit and offset must be integers.", 400)

    query = get_supabase().table("events").select("id,organizer_id,title,capacity,status")
    if event_status:
        query = query.eq("status", event_status)
    rows = query.order("title").range(offset, offset + limit - 1).execute().data
    counts = fetch_registration_counts([str(row["id"]) for row in rows])
    return jsonify([add_registration_count(row, counts) for row in rows])


@app.get("/api/events/<event_id>")
def get_event(event_id: str):
    try:
        event_id = parse_uuid(event_id, "event_id")
    except ValueError as exc:
        return error_response(str(exc), 400)

    rows = (
        get_supabase()
        .table("events")
        .select("id,organizer_id,title,capacity,status")
        .eq("id", event_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return error_response("Event not found.", 404)
    counts = fetch_registration_counts([event_id])
    return jsonify(add_registration_count(rows[0], counts))


@app.post("/api/registrations")
def create_registration():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object.", 422)
    try:
        authenticated_user_id = parse_user_header()
    except ValueError as exc:
        return error_response(str(exc), 401)

    try:
        event_id = parse_uuid(payload.get("event_id"), "event_id")
        supplied_user_id = payload.get("user_id")
        if supplied_user_id is not None:
            supplied_user_id = parse_uuid(supplied_user_id, "user_id")
            if supplied_user_id != authenticated_user_id:
                return error_response(
                    "user_id must match the authenticated user.", 403
                )
        user_id = authenticated_user_id
    except ValueError as exc:
        return error_response(str(exc), 422)

    client = get_supabase()
    user = client.table("users").select("id").eq("id", user_id).limit(1).execute().data
    event_rows = (
        client.table("events")
        .select("id,capacity,status")
        .eq("id", event_id)
        .limit(1)
        .execute()
        .data
    )
    if not user:
        return error_response("User not found.", 404)
    if not event_rows:
        return error_response("Event not found.", 404)
    event = event_rows[0]
    if event["status"] != "published":
        return error_response("Registrations are closed for this event.", 409)

    existing = (
        client.table("registrations")
        .select("id")
        .eq("user_id", user_id)
        .eq("event_id", event_id)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        return error_response("User is already registered for this event.", 409)

    registered = (
        client.table("registrations")
        .select("id", count="exact")
        .eq("event_id", event_id)
        .execute()
    )
    if (registered.count or 0) >= event["capacity"]:
        return error_response("Event capacity has been reached.", 409)

    try:
        created_at = datetime.now(timezone.utc).isoformat()
        created = (
            client.table("registrations")
            .insert({"user_id": user_id, "event_id": event_id, "created_at": created_at})
            .execute()
            .data
        )
    except APIError as exc:
        if getattr(exc, "code", None) == "23505":
            return error_response("User is already registered for this event.", 409)
        raise

    if not created:
        return error_response("Registration could not be created.", 500)
    return jsonify(created[0]), 201


@app.get("/api/me/registrations")
def list_my_registrations():
    try:
        user_id = parse_user_header()
    except ValueError as exc:
        return error_response(str(exc), 400)
    rows = (
        get_supabase()
        .table("registrations")
        .select("id,user_id,event_id,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    return jsonify(rows)


@app.get("/api/events/<event_id>/registrations")
def list_event_registrations(event_id: str):
    try:
        event_id = parse_uuid(event_id, "event_id")
        user_id = parse_user_header()
    except ValueError as exc:
        return error_response(str(exc), 400)

    event_rows = (
        get_supabase()
        .table("events")
        .select("organizer_id")
        .eq("id", event_id)
        .limit(1)
        .execute()
        .data
    )
    if not event_rows:
        return error_response("Event not found.", 404)
    if str(event_rows[0]["organizer_id"]) != user_id:
        return error_response("Only the event organizer can view attendees.", 403)

    rows = (
        get_supabase()
        .table("registrations")
        .select("id,user_id,event_id,created_at")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
        .data
    )
    return jsonify(rows)


@app.get("/health")
def health_check():
    try:
        get_supabase().table("events").select("id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 - health endpoint must return JSON.
        logger.warning("Supabase health check failed: %s", exc)
        return jsonify({"status": "degraded", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "ok"})


@app.errorhandler(APIError)
def handle_supabase_error(error: APIError):
    logger.exception("Supabase request failed", exc_info=error)
    return error_response("Database request failed.", 502)


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    logger.exception("Unhandled application error", exc_info=error)
    return error_response("Internal server error.", 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
