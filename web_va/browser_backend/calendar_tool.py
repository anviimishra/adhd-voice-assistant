import os
import json
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
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
        return str(e)

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

        if "T" in start:
            time_str = start.split("T")[1][:5]
        else:
            time_str = "All day"

        lines.append(f"{time_str} — {title}")

    return "\n".join(lines)


def add_event(summary: str, start_time: str, end_time: str, description: str = "") -> dict:
    """
    Add an event to Google Calendar.
    
    Args:
        summary: Event title (e.g., "Team meeting")
        start_time: ISO format datetime (e.g., "2025-12-01T14:00:00")
        end_time: ISO format datetime (e.g., "2025-12-01T15:00:00")
        description: Optional event description
    
    Returns:
        dict: The created event from Google Calendar API
    """
    service = get_calendar_service()
    
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/New_York',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'America/New_York',
        },
    }
    
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return created_event


def get_next_free_slots(count: int = 3, min_duration_minutes: int = 15) -> list:
    """
    Find the next 'count' available time slots in the calendar.
    Returns list of datetime objects representing start times.
    
    Args:
        count: Number of free slots to find
        min_duration_minutes: Minimum slot duration needed
    
    Returns:
        List of datetime objects (timezone-aware)
    """
    service = get_calendar_service()
    
    # Start from current time, round up to next 15-min interval
    now = datetime.now(timezone.utc)
    minutes_to_add = 15 - (now.minute % 15)
    search_start = now + timedelta(minutes=minutes_to_add)
    search_start = search_start.replace(second=0, microsecond=0)
    
    # Search window: next 7 days
    search_end = search_start + timedelta(days=7)
    
    # Get all events in this window
    events_result = service.events().list(
        calendarId='primary',
        timeMin=search_start.isoformat(),
        timeMax=search_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    # Build list of busy periods
    busy_periods = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        
        # Skip all-day events
        if 'T' not in start:
            continue
        
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        busy_periods.append((start_dt, end_dt))
    
    # Find free slots
    free_slots = []
    current_time = search_start
    
    # Only search during waking hours (8am - 10pm)
    while len(free_slots) < count and current_time < search_end:
        # Skip nighttime hours
        local_hour = current_time.astimezone().hour
        if local_hour < 8 or local_hour >= 22:
            # Jump to next 8am
            current_time = current_time.replace(hour=8, minute=0, second=0)
            current_time += timedelta(days=1)
            continue
        
        slot_end = current_time + timedelta(minutes=min_duration_minutes)
        
        # Check if this slot overlaps with any busy period
        is_free = True
        for busy_start, busy_end in busy_periods:
            if current_time < busy_end and slot_end > busy_start:
                # Overlaps with busy period
                is_free = False
                # Jump to end of this busy period
                current_time = busy_end
                break
        
        if is_free:
            free_slots.append(current_time)
            current_time = slot_end
        else:
            # Round up to next 15-min interval after the busy period
            minutes_to_add = 15 - (current_time.minute % 15)
            if minutes_to_add == 15:
                minutes_to_add = 0
            current_time += timedelta(minutes=minutes_to_add)
    
    return free_slots