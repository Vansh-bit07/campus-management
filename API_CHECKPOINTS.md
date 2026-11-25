# API checkpoints

This checklist is the acceptance contract for the Events API. It follows the
API diagram and the `users`, `events`, and `registrations` tables shown in the
database diagram.

## Contract checkpoints

| # | Checkpoint | Expected result |
|---|---|---|
| 1 | `GET /` | Returns service metadata and links to the API and health check. |
| 2 | `GET /health` | Returns `200` with `{"status":"ok","database":"ok"}` when Supabase is reachable; returns `503` with a degraded JSON response when it is not. |
| 3 | `GET /api/events` | Returns published and other events, with optional `status`, `limit`, and `offset` query parameters, plus `registration_count`. |
| 4 | `GET /api/events/{id}` | Returns one event or `404` when the UUID does not exist. |
| 5 | `POST /api/registrations` | Requires `X-User-Id`; accepts `{"event_id":"<uuid>"}` and returns `201`. Missing identity returns `401`; duplicate, closed, and full events return `409`; missing events return `404`. |
| 6 | `GET /api/me/registrations` | Requires `X-User-Id` and returns only that user’s registrations. |
| 7 | `GET /api/events/{id}/registrations` | Requires the event organizer’s `X-User-Id`; non-organizers receive `403`. |

The optional `user_id` in the registration body is retained for client
compatibility, but it must equal `X-User-Id`. The header is the source of
identity and prevents a caller from registering on behalf of another user.

## Database checkpoints

- `users.id`, `events.id`, and `registrations.id` are UUIDs.
- `events.organizer_id` references `users.id`.
- `registrations.user_id` references `users.id`.
- `registrations.event_id` references `events.id`.
- `registrations.created_at` is a timestamp with timezone.
- Add a unique constraint on `(user_id, event_id)` to protect against duplicate
  registrations under concurrent requests.
- Keep RLS enabled and grant the server key only the operations used by this
  service.

## Render release checklist

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`
- Health check path: `/health`
- Set `SUPABASE_URL` and `SUPABASE_KEY` as Render secret environment values.
- Set `CORS_ORIGINS` to the exact deployed frontend origin(s); do not leave `*`
  enabled for a production frontend.
- Confirm the deployed service responds to `/health` before connecting the UI.

## Local verification

```powershell
python -m unittest discover -s tests -v
```
