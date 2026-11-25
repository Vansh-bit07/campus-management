# Events API

Flask backend for the events API, backed by Supabase. The existing API contract is preserved:

- `GET /api/events`
- `GET /api/events/{id}`
- `POST /api/registrations`
- `GET /api/me/registrations` with `X-User-Id`
- `GET /api/events/{id}/registrations` with organizer `X-User-Id`
- `GET /health`

Authentication remains intentionally disabled to preserve the original contract. The `X-User-Id` header and `user_id` request field are temporary identity mechanisms and should be replaced with Supabase Auth before exposing private data publicly.

## Requirements

- Python 3.12+
- A Supabase project with `users`, `events`, and `registrations` tables matching the existing schema.
- Data API access and appropriate RLS policies/grants for the key used by the server.

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` with your Supabase project URL and server-side key. Never commit `.env` or paste credentials into source code. Start the development server with:

```powershell
python app.py
```

The API is available at `http://127.0.0.1:5000`; the health check is `/health`.

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Server-side Supabase key kept only in environment variables |
| `CORS_ORIGINS` | No | Comma-separated allowed origins; defaults to `*` for compatibility |
| `LOG_LEVEL` | No | Python logging level; defaults to `INFO` |
| `PORT` | No | Local port; Render supplies this automatically |

## Render deployment

Create a Render Web Service connected to this repository and the `main` branch. `render.yaml` defines:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT app:app`
- Health check: `/health`

In Render's Environment settings, set `SUPABASE_URL` and `SUPABASE_KEY` as secret values. Set `CORS_ORIGINS` to the exact frontend origin(s) in production instead of `*`. Render provides `PORT`; the Gunicorn command binds to it.

## Security notes

Do not commit Supabase keys, `.env`, database dumps, or tokens. Keep RLS enabled and grant only the operations required by this API. The current temporary-header authentication is not sufficient for production authorization; add Supabase Auth and verify access tokens before treating this API as production-ready for private user data.
