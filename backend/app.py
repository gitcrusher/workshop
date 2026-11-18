import os
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from postgrest import APIError
from supabase import Client, create_client

load_dotenv()

app = Flask(__name__)

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
supabase: Client | None = (
    create_client(supabase_url, supabase_key)
    if supabase_url and supabase_key
    else None
)


@app.after_request
def add_cors_headers(response):
    """Allow browser clients from any origin to call this API."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def database():
    if supabase is None:
        return None, (jsonify(error="Database is not configured"), 503)
    return supabase, None


def valid_uuid(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def database_error(error):
    app.logger.exception("Supabase request failed: %s", error)
    return jsonify(error="Database request failed"), 500


@app.route("/", methods=["GET", "OPTIONS"])
def index():
    return jsonify(service="events-api")


@app.route("/api/events", methods=["GET", "OPTIONS"])
def list_events():
    client, error = database()
    if error:
        return error
    try:
        query = client.table("events").select("id, organizer_id, title, capacity, status")
        status = request.args.get("status")
        if status:
            query = query.eq("status", status)
        return jsonify(query.execute().data), 200
    except APIError as exc:
        return database_error(exc)


@app.route("/api/events/<event_id>", methods=["GET", "OPTIONS"])
def get_event(event_id):
    event_id = valid_uuid(event_id)
    if not event_id:
        return jsonify(error="event id must be a valid UUID"), 400
    client, error = database()
    if error:
        return error
    try:
        response = (
            client.table("events")
            .select("id, organizer_id, title, capacity, status")
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return jsonify(error="Event not found"), 404
        return jsonify(response.data[0]), 200
    except APIError as exc:
        return database_error(exc)


@app.route("/api/registrations", methods=["POST", "OPTIONS"])
def create_registration():
    payload = request.get_json(silent=True) or {}
    user_id = valid_uuid(payload.get("user_id"))
    event_id = valid_uuid(payload.get("event_id"))
    if not user_id or not event_id:
        return jsonify(error="user_id and event_id must be valid UUIDs"), 400

    client, error = database()
    if error:
        return error
    try:
        event_response = (
            client.table("events")
            .select("id, capacity, status")
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
        if not event_response.data:
            return jsonify(error="Event not found"), 404
        event = event_response.data[0]
        if event.get("status") != "open":
            return jsonify(error="Event is not open for registration"), 409

        duplicate = (
            client.table("registrations")
            .select("id")
            .eq("user_id", user_id)
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        if duplicate.data:
            return jsonify(error="User is already registered for this event"), 409

        registrations = (
            client.table("registrations")
            .select("id", count="exact")
            .eq("event_id", event_id)
            .execute()
        )
        capacity = event.get("capacity")
        if capacity is not None and registrations.count is not None and registrations.count >= capacity:
            return jsonify(error="Event is full"), 409

        created = (
            client.table("registrations")
            .insert({"user_id": user_id, "event_id": event_id})
            .execute()
        )
        return jsonify(created.data[0]), 201
    except APIError as exc:
        # Concurrent duplicate inserts may be rejected by a database constraint.
        if getattr(exc, "code", None) == "23505":
            return jsonify(error="User is already registered for this event"), 409
        return database_error(exc)


@app.route("/api/me/registrations", methods=["GET", "OPTIONS"])
def my_registrations():
    user_id = valid_uuid(request.args.get("user_id"))
    if not user_id:
        return jsonify(error="user_id query parameter must be a valid UUID"), 400
    client, error = database()
    if error:
        return error
    try:
        response = (
            client.table("registrations")
            .select("id, user_id, event_id, created_at, events(id, title, status, capacity)")
            .eq("user_id", user_id)
            .execute()
        )
        return jsonify(response.data), 200
    except APIError as exc:
        return database_error(exc)


@app.route("/api/events/<event_id>/registrations", methods=["GET", "OPTIONS"])
def event_registrations(event_id):
    event_id = valid_uuid(event_id)
    organizer_id = valid_uuid(request.args.get("organizer_id"))
    if not event_id:
        return jsonify(error="event id must be a valid UUID"), 400
    if not organizer_id:
        return jsonify(error="organizer_id query parameter must be a valid UUID"), 400

    client, error = database()
    if error:
        return error
    try:
        event = (
            client.table("events")
            .select("organizer_id")
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
        if not event.data:
            return jsonify(error="Event not found"), 404
        # Without authentication, this is only a caller-supplied check and is
        # not a security boundary: a client can submit another organizer's ID.
        if event.data[0].get("organizer_id") != organizer_id:
            return jsonify(error="Organizer does not own this event"), 403

        response = (
            client.table("registrations")
            .select("id, user_id, event_id, created_at, users(id, email, role)")
            .eq("event_id", event_id)
            .execute()
        )
        return jsonify(response.data), 200
    except APIError as exc:
        return database_error(exc)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
