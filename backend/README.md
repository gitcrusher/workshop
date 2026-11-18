# Events API

Flask API backed by Supabase. Render deployment settings are in `render.yaml`.

## Deploy on Render

1. Push this backend directory to a Git repository.
2. In Render, create a **Blueprint** and select that repository. If the backend is a subdirectory in the repository, set the Blueprint's root directory to `backend`.
3. Render uses `pip install -r requirements.txt` to build and `gunicorn app:app --bind 0.0.0.0:$PORT` to start the service.
4. Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in the Render service environment. The Blueprint prompts for both values.

The `.env` file is for local use and is excluded from Git. Do not upload or commit it. The app returns a clear 503 response when its Supabase settings are missing.

## API

- `GET /api/events` (optional `?status=...`)
- `GET /api/events/<event_id>`
- `POST /api/registrations` with JSON `{ "user_id": "...", "event_id": "..." }`
- `GET /api/me/registrations?user_id=...`
- `GET /api/events/<event_id>/registrations?organizer_id=...`

CORS currently allows every origin, and the API does not authenticate callers. The supplied user and organizer IDs are therefore not verified identities; this is not suitable for protecting private attendee data.
