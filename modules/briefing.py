import json
import datetime
from typing import List, Dict, Any, Tuple
from modules.ai_client import call_gemini_with_retry

def summarize_and_process(emails: List[Dict[str, Any]], calendar_events: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Constructs the prompt for Gemini, extracts new Life Admin events, smart replies,
    and generates the Daily Briefing HTML output.
    Returns (raw_json_response, model_used).
    """
    sanitized_calendar = []
    for e in calendar_events:
        start = e.get('start', {})
        date_str = start.get('date') or start.get('dateTime', '')[:10]
        sanitized_calendar.append({
            "summary": e.get('summary'),
            "date": date_str,
            "description": e.get('description', '')[:500]
        })

    prompt = f"""
    You are a high-end personal executive assistant and Life Admin expert.
    
    CONTEXT:
    Date: {datetime.date.today().strftime('%A, %B %d, %Y')}
    Recent Emails: {json.dumps(emails)}
    Upcoming Calendar (Next 30 Days): {json.dumps(sanitized_calendar)}

    TASK 1: Extract Life Admin & Deliveries from Emails
    - Extract future appointments, deadlines, renewals, travel bookings, and package deliveries mentioned in emails.
    - For each item, provide:
      - `summary`: Event title
      - `date`: "YYYY-MM-DD"
      - `description`: Detailed summary of context from email, including direct vendor/tracking links if available.

    TASK 2: Smart Replies
    - Identify emails that clearly require a personal reply (not spam/notifications).
    - For each, write a short, professional, and helpful draft reply.

    TASK 3: Create a Daily Briefing (HTML)
    - Professional CSS, deep blue theme (`#1e293b` / `#0f172a`, clear typography).
    - Sections:
      1. Executive TL;DR
      2. Deliveries & Life Admin Highlights
      3. Smart Drafts Created
      4. Look Ahead / Upcoming Events (Must list ALL upcoming calendar events with dates, direct booking/info links, and key reminders so the user is kept informed daily).

    OUTPUT FORMAT:
    Return a valid JSON object:
    {{
      "html": "...",
      "new_calendar_events": [
        {{
          "summary": "...",
          "date": "YYYY-MM-DD",
          "description": "..."
        }}
      ],
      "smart_replies": [
        {{
          "to": "...",
          "subject": "...",
          "content": "...",
          "messageId": "..."
        }}
      ]
    }}
    """
    
    res, model_used = call_gemini_with_retry(
        contents=prompt,
        config={'response_mime_type': 'application/json'}
    )
    return res.text, model_used
