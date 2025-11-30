# calendar_tool.py
import os
import json
from datetime import datetime, timezone

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"


def _load_credentials():
    """Load saved user credentials from token.json, if they exist and are valid."""
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "I don't have access to your Google Calendar yet. "
            "Open http://localhost:5050/calendar/auth in your browser to connect it."
        )

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        # Could also refresh here if refresh_token present; keeping it simple.
        raise RuntimeError(
            "Your Google Calendar login expired. "
            "Open http://localhost:5050/calendar/auth again to reconnect."
        )
    return creds


def get_calendar_service():
    """Return an authenticated Google Calendar service using saved credentials."""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    return service


def get_today_schedule() -> str:
    """
    Return today's remaining events in a human-readable string.
    If not authorized, returns a message telling the user how to connect.
    """
    try:
        service = get_calendar_service()
    except RuntimeError as e:
        # Return the message so ADHDWiz can paraphrase / surface it
        return str(e)

    # Use UTC to be safe (you can adapt to local tz if you want)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    end_iso = end_of_day.isoformat()

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    if not events:
        return "You have no events for the rest of today. 💆‍♀️"

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        title = event.get("summary", "Untitled event")

        # Datetime vs all-day
        if "T" in start:
            # Example: 2025-11-30T14:00:00-05:00 -> "14:00"
            time_str = start.split("T")[1][:5]
        else:
            time_str = "All day"

        lines.append(f"{time_str} — {title}")

    return "\n".join(lines)
