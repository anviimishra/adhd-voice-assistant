from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from calendar_tool import get_today_schedule, add_event, get_next_free_slots
from tabs_retriever import group_tabs_for_subtasks, retriever_has_tabs


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
    - Detects if user wants tab organization
    - Otherwise responds in ADHDWiz voice
    """
    user_lower = user_message.lower()

    # -------------------------------------------------
    # 0. EXPLICIT TAB ORGANIZATION REQUESTS
    # -------------------------------------------------
    tab_triggers = [
        "organize tabs",
        "organise tabs",
        "help with tabs",
        "relevant tabs",
        "which tabs",
        "what tabs",
        "tabs for",
        "show tabs",
        "find tabs for",
        "help me focus on",
    ]

    if any(trigger in user_lower for trigger in tab_triggers):
        try:
            results = get_relevant_tabs_flat(user_message)

            if results.get("error"):
                return "I couldn't find any synced tabs yet. Try syncing them first."

            task = results["task"]
            tabs = results["tabs"]

            if not tabs:
                return f"I looked at your tabs but didn’t find anything relevant to {task}."

            response = [f"Here are the tabs most relevant to {task}:"]

            for tab in tabs:
                title = tab.get("title") or "(no title)"
                url = tab.get("url") or ""
                response.append(f"- {title} ({url})")

            return "\n".join(response).strip()

        except Exception as e:
            print("Tab organization error:", e)
            return "Something went wrong while organizing your tabs."


        except Exception as e:
            print(f"Tab organization error: {e}")
            # Fall through to normal behavior if something explodes
            pass

    # -------------------------------------------------
    # 1. DETECT TASK OVERWHELM / STARTING CONFUSION
    # -------------------------------------------------
    overwhelm_triggers = [
        "don't know where to start",
        "dont know where to start",
        "don't know how to start",
        "dont know how to start",
        "overwhelmed",
        "too much",
        "can't start",
        "cant start",
        "stuck",
        "procrastinating",
        "need to do",
        "have to do",
        "should do",
        "supposed to",
        "paralyzed",
        "paralysed",
        "freezing",
        "can't focus on",
        "cant focus on",
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
I hear you — {breakdown['task_name']} feels like a lot right now. Let's make it tiny.

I broke it into 3 micro-steps and added them to your calendar:

"""
            for i, evt in enumerate(added_events, 1):
                response += f"{i}. {evt['name']} — {evt['time']} ({evt['duration']} min)\n"
            
            response += """
You don't have to do it all at once. Just show up for step 1. That's it.

The rest will follow. You've got this.
"""
            
            return response.strip()
        
        except Exception as e:
            print(f"Task breakdown error: {e}")
            # Fall through to normal response if this fails
            pass

    # -------------------------------------------------
    # 2. Detect explicit event creation requests
    # -------------------------------------------------
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
Got it. I added "{event_details['summary']}" to your calendar.

When: {event_details['start_time'].split('T')[0]} at {event_details['start_time'].split('T')[1][:5]}

You are all set. Need anything else?
            """.strip()
        
        except Exception as e:
            return f"I had trouble adding that event. Could you try again with a bit more detail? (Error: {str(e)})"

    # -------------------------------------------------
    # 3. Detect schedule queries
    # -------------------------------------------------
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
        Use short paragraphs and reassuring words.
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are ADHDWiz, a supportive ADHD coach."},
                {"role": "user", "content": prompt}
            ]
        )

        return completion.choices[0].message.content.strip()

    # -------------------------------------------------
    # 4. Normal ADHDWiz chat (no tools)
    # -------------------------------------------------
    system_prompt = """
    You are ADHDWiz — a warm, non-judgmental ADHD support assistant.
    
    Write in plain text only.
    Do not use any emojis.
    Do not use asterisks, bold, italics, markdown, or bullets.
    Do not use lists or special characters.
    Avoid symbols like *, -, •, >, _, or fancy formatting.

    Style:
    - short paragraphs
    - supportive, casual tone
    - micro-steps (30–60 seconds)
    - no shame, lots of validation
    
    When users express confusion or overwhelm about tasks, your responses should
    acknowledge their feelings and offer encouragement.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    tools = [
        {
            "name": "get_relevant_tab_groups",
            "description": "Find the browser tabs that best support a task and group them by micro-subtasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "What the user is trying to accomplish. Example: 'Finish my biology lab writeup'."
                    }
                },
                "required": ["task_description"]
            }
        }
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        functions=tools,
        # IMPORTANT CHANGE: do not auto-call tools anymore
        function_call="none",
        temperature=0.85
    )

    first_choice = completion.choices[0].message

    # With function_call="none", this block is basically dead code now,
    # but we leave it for minimal-diff compatibility.
    if getattr(first_choice, "function_call", None):
        func_name = first_choice.function_call.name
        if func_name == "get_relevant_tab_groups":
            try:
                args = json.loads(first_choice.function_call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            tool_payload = get_relevant_tab_groups(args.get("task_description", user_message))

            messages.append({
                "role": first_choice.role,
                "content": first_choice.content,
                "function_call": {
                    "name": func_name,
                    "arguments": first_choice.function_call.arguments
                }
            })
            messages.append({
                "role": "function",
                "name": func_name,
                "content": json.dumps(tool_payload)
            })

            followup = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.75
            )
            return followup.choices[0].message.content.strip()

    return first_choice.content.strip()


def generate_study_plan_from_syllabus(syllabus_text: str) -> str:
    """
    Produce an ADHD-friendly study plan derived from syllabus text.
    """
    context = (syllabus_text or "").strip()
    if len(context) > 6000:
        context = context[:6000]

    prompt = f"""
You are ADHDWiz, a compassionate focus coach.

Create a motivational week-by-week study roadmap from the syllabus notes below.
Each week should include:
- Theme or chapter focus
- 2-3 micro-actions (prefer verbs)
- Estimated total hours
- Tiny accountability or reward idea

If info is missing, infer reasonable topics and keep it 6-8 weeks long.

Syllabus notes:
\"\"\"{context or "No syllabus text was provided. Build a balanced 6-week plan for a college course."}\"\"\"
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You design concise, ADHD-friendly study roadmaps."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    return response.choices[0].message.content.strip()


def extract_core_task(user_message: str) -> str:
    """
    Extract the actual study/task topic from natural language.
    Uses GPT to strip away phrases like:
    - "find tabs for"
    - "organize tabs for"
    - "help me with"
    - "I need to study"
    
    Returns only the keywords describing the academic task.
    """

    prompt = f"""
    Extract ONLY the core academic or study topic from this message:
    "{user_message}"

    Rules:
    - Remove phrases like "find tabs for", "organize tabs", "help with", etc.
    - Return ONLY the subject/topic, not a full sentence.
    - Keep it short: 3–8 words max.
    - Examples:
        "find tabs for linear algebra midterm" -> "linear algebra midterm"
        "help me study for biology exam" -> "biology exam"
        "organize tabs for my stats homework" -> "statistics homework"
        "what tabs should I use for discrete structures" -> "discrete structures"
    - Respond with plain text only (no JSON).
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract the clean academic topic only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()

def get_relevant_tabs_flat(task_description: str) -> dict:
    raw = (task_description or "").strip()

    if not retriever_has_tabs():
        return {"task": raw, "tabs": [], "error": "No synced tabs available."}

    try:
        # STEP 1 — Extract clean academic task
        core_task = extract_core_task(raw)

        # STEP 2 — perform semantic search
        from tabs_retriever import _retriever
        matches = _retriever.search(core_task, top_k=10, min_score=0.03)

        # IMPORTANT — Pull tabId from original tab list
        flat_results = []
        for m in matches:
            for t in _retriever.tabs:
                if t["url"] == m["url"]:    # match exact tab
                    m["id"] = t.get("id")    # append tabId for grouping
                    break
            flat_results.append(m)

        return {
            "task": core_task,
            "tabs": flat_results,
            "source": "flat-search"
        }

    except Exception as exc:
        return {"task": raw, "tabs": [], "error": str(exc)}
