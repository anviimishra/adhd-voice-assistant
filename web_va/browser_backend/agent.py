# agent.py
from openai import OpenAI
import os
from dotenv import load_dotenv


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from calendar_tool import get_today_schedule

def ADHDWiz_respond(user_message: str) -> str:
    """
    Main AI agent:
    - Detects if user wants schedule summary
    - Otherwise responds in ADHDWiz voice
    """

    user_lower = user_message.lower()

    schedule_triggers = [
        "schedule",
        "what do i have",
        "what's next",
        "what is next",
        "my day",
        "today",
        "afternoon",
        "evening",
        "morning",
        "calendar",
        "plan",
        "plans",
        "busy",
        "overwhelmed",
        "what am i supposed to do"
    ]

    # 1. Detect schedule confusion
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


    # 2. Normal ADHDWiz chat
    system_prompt = """
    You are ADHDWiz — a warm, non-judgmental ADHD support assistant.

    Style:
    - short paragraphs or bullet points
    - supportive, casual tone
    - micro-steps (30–60 seconds)
    - no shame, lots of validation
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
