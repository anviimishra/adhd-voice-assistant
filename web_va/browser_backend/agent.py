from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from calendar_tool import get_today_schedule, add_event, get_next_free_slots


def parse_event_from_message(user_message: str) -> dict:
    """
    Use GPT to extract event details from natural language.
    Returns dict with summary, start_time, end_time, description
    """
    prompt = f"""
    Extract calendar event details from this message: "{user_message}"
    
    Return ONLY a JSON object with these fields:
    {{
        "summary": "event title",
        "start_time": "2025-12-01T14:00:00",
        "end_time": "2025-12-01T15:00:00",
        "description": "optional description"
    }}
    
    Rules:
    - Use ISO format for times (YYYY-MM-DDTHH:MM:SS)
    - If no date specified, assume today
    - If no end time specified, assume 1 hour duration
    - If time is vague (e.g., "afternoon"), use 2 PM
    - Current date/time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a calendar event parser. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    
    result = response.choices[0].message.content.strip()
    result = re.sub(r'```json\n?|\n?```', '', result)
    
    return json.loads(result)


def break_task_into_subtasks(user_message: str, context: str = "") -> dict:
    """
    Use GPT to detect task overwhelm and break into 3 micro-subtasks.
    Returns dict with task_name and list of 3 subtasks with durations.
    """
    prompt = f"""
    The user said: "{user_message}"
    
    {f"Context: {context}" if context else ""}
    
    They seem overwhelmed or confused about starting a task. Break it into exactly 3 tiny, actionable subtasks.
    
    Return ONLY a JSON object:
    {{
        "task_name": "Main task name",
        "subtasks": [
            {{"name": "Subtask 1", "duration_minutes": 5}},
            {{"name": "Subtask 2", "duration_minutes": 10}},
            {{"name": "Subtask 3", "duration_minutes": 15}}
        ]
    }}
    
    Rules:
    - Each subtask should take 5-20 minutes max
    - Make them ADHD-friendly: specific, tiny, achievable
    - Start with the absolute easiest micro-step
    - Use action verbs ("Open laptop", "Find one source", "Write first sentence")
    - Duration should reflect realistic time needed
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an ADHD task-breaking expert. Be specific and compassionate."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    
    result = response.choices[0].message.content.strip()
    result = re.sub(r'```json\n?|\n?```', '', result)
    
    return json.loads(result)


def ADHDWiz_respond(user_message: str) -> str:
    """
    Main AI agent:
    - Detects task overwhelm and auto-creates subtask calendar blocks
    - Detects if user wants to add an event
    - Detects if user wants schedule summary
    - Otherwise responds in ADHDWiz voice
    """
    user_lower = user_message.lower()

    # 1. DETECT TASK OVERWHELM / STARTING CONFUSION
    overwhelm_triggers = [
        "don't know where to start",
        "don't know how to start",
        "overwhelmed",
        "too much",
        "can't start",
        "stuck",
        "procrastinating",
        "need to do",
        "have to do",
        "should do",
        "supposed to",
        "paralyzed",
        "freezing",
        "can't focus on"
    ]
    
    if any(trigger in user_lower for trigger in overwhelm_triggers):
        try:
            # Break task into subtasks
            breakdown = break_task_into_subtasks(user_message)
            
            # Get next available time slots
            free_slots = get_next_free_slots(count=3)
            
            # Add each subtask to calendar
            added_events = []
            for i, subtask in enumerate(breakdown["subtasks"]):
                if i < len(free_slots):
                    slot = free_slots[i]
                    duration = timedelta(minutes=subtask["duration_minutes"])
                    
                    event = add_event(
                        summary=f"✅ {subtask['name']}",
                        start_time=slot.isoformat(),
                        end_time=(slot + duration).isoformat(),
                        description=f"Part {i+1} of: {breakdown['task_name']}"
                    )
                    
                    added_events.append({
                        "name": subtask["name"],
                        "time": slot.strftime("%I:%M %p"),
                        "duration": subtask["duration_minutes"]
                    })
            
            # Generate encouraging response
            response = f"""
I hear you — **{breakdown['task_name']}** feels like a lot right now. Let's make it tiny.

I broke it into 3 micro-steps and added them to your calendar:

"""
            for i, evt in enumerate(added_events, 1):
                response += f"{i}. **{evt['name']}** — {evt['time']} ({evt['duration']} min)\n"
            
            response += f"""
You don't have to do it all at once. Just show up for step 1. That's it.

The rest will follow. You've got this.
            """
            
            return response.strip()
        
        except Exception as e:
            print(f"Task breakdown error: {e}")
            # Fall through to normal response if this fails
            pass

    # 2. Detect explicit event creation requests
    add_event_triggers = [
        "add event",
        "create event",
        "schedule",
        "remind me",
        "block time",
        "put on calendar",
        "add to calendar",
        "meeting at",
        "appointment"
    ]
    
    if any(trigger in user_lower for trigger in add_event_triggers):
        try:
            event_details = parse_event_from_message(user_message)
            
            created_event = add_event(
                summary=event_details["summary"],
                start_time=event_details["start_time"],
                end_time=event_details["end_time"],
                description=event_details.get("description", "")
            )
            
            return f"""
✅ Got it! I added "{event_details['summary']}" to your calendar.

📅 **When**: {event_details['start_time'].split('T')[0]} at {event_details['start_time'].split('T')[1][:5]}

You're all set! Need anything else? 🌟
            """.strip()
        
        except Exception as e:
            return f"Hmm, I had trouble adding that event. Could you try again with more details? (Error: {str(e)})"

    # 3. Detect schedule queries
    schedule_triggers = [
        "what do i have",
        "what's next",
        "what is next",
        "my day",
        "today",
        "calendar",
        "busy",
        "what am i supposed to do"
    ]

    if any(trigger in user_lower for trigger in schedule_triggers):
        schedule_text = get_today_schedule()

        prompt = f"""
        You are ADHDWiz. The user's schedule is:

        {schedule_text}

        Summarize this in a warm, ADHD-friendly tone.
        Use bullet points and reassuring words.
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are ADHDWiz, a supportive ADHD coach."},
                {"role": "user", "content": prompt}
            ]
        )

        return completion.choices[0].message.content.strip()

    # 4. Normal ADHDWiz chat
    system_prompt = """
    You are ADHDWiz — a warm, non-judgmental ADHD support assistant.
    
    Write in plain text only.
    Do not use any emojis.
    Do not use asterisks, bold, italics, markdown, or bullets.
    Do not use lists or special characters.
    Avoid symbols like *, -, •, >, _, or fancy formatting.

    Style:
    - short paragraphs or bullet points
    - supportive, casual tone
    - micro-steps (30–60 seconds)
    - no shame, lots of validation
    
    When users express confusion or overwhelm about tasks, your responses should
    acknowledge their feelings and offer encouragement.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.85
    )

    return completion.choices[0].message.content.strip()