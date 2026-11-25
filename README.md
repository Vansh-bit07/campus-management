# Events backend

This is a small FastAPI backend implementing the API contract in `api.png` over the tables shown in `database.png`. It is ready to deploy on Render.

Authentication is intentionally disabled. For the two user-specific endpoints, pass the temporary user UUID in `X-User-Id`. Registration requests include `user_id` in the JSON body until a real authentication flow is added.

## Run

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation. The SQLite database is created as `events.db` on first startup and includes one organizer, one attendee, and one published event.

## Deploy to Render

Create a new Render Web Service from this repository. Render will use `render.yaml`, install `requirements.txt`, and start the API with the required host and port settings. The included SQLite database uses Render's temporary filesystem; use a managed database before production use.

## Endpoints

- `GET /api/events`
- `GET /api/events/{id}`
- `POST /api/registrations`
- `GET /api/me/registrations` with `X-User-Id`
- `GET /api/events/{id}/registrations` with organizer `X-User-Id`
