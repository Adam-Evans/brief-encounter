import re
import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional

def normalize_title(title: str) -> str:
    """
    Normalizes event titles for fuzzy deduplication comparison by converting to lowercase
    and stripping all non-alphanumeric characters.
    """
    if not title:
        return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def is_ai_processed(event: Dict[str, Any]) -> bool:
    """
    Checks if a calendar event has frontmatter tags indicating it was already processed/enriched by AI.
    """
    desc = event.get('description', '')
    if not desc:
        return False
    return 'ai_processed: true' in desc and 'ai_model:' in desc

def format_frontmatter(source: str, model: str, date_str: Optional[str] = None) -> str:
    """
    Generates standardized YAML frontmatter header string for calendar event descriptions.
    """
    if date_str is None:
        date_str = datetime.date.today().isoformat()
    return f"---\nai_processed: true\nai_source: {source}\nai_model: {model}\nai_updated: {date_str}\n---\n\n"

def deduplicate_calendar_events(service: Any, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scans calendar events for duplicates (matching normalized title and start date).
    Keeps the best event instance and deletes duplicate entries from Google Calendar.
    """
    grouped = defaultdict(list)
    for e in events:
        title = e.get('summary', '').strip()
        start = e.get('start', {})
        date_str = start.get('date') or start.get('dateTime', '')[:10]
        if not date_str:
            continue
        norm_key = (normalize_title(title), date_str)
        grouped[norm_key].append(e)

    clean_events = []
    deleted_count = 0
    for norm_key, group in grouped.items():
        if len(group) > 1:
            group.sort(key=lambda x: (
                'ai_processed: true' in x.get('description', ''),
                'ai_model:' in x.get('description', ''),
                len(x.get('description', ''))
            ), reverse=True)
            keeper = group[0]
            clean_events.append(keeper)
            for duplicate in group[1:]:
                try:
                    service.events().delete(calendarId='primary', eventId=duplicate['id']).execute()
                    print(f"Deleted duplicate calendar event: '{duplicate.get('summary')}' (ID: {duplicate['id']}) on {norm_key[1]}")
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting duplicate event {duplicate['id']}: {e}")
        else:
            clean_events.append(group[0])

    if deleted_count > 0:
        print(f"Deduplication complete: removed {deleted_count} duplicate calendar events.")
    else:
        print("No duplicate calendar events found.")

    return clean_events

def fetch_calendar_events(service: Any, days: int = 30) -> List[Dict[str, Any]]:
    """
    Fetches upcoming primary calendar events for the next specified days.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()
    
    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=future_date,
        maxResults=50, singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

def add_calendar_event(service: Any, summary: str, date_str: str, description: str = "", existing_events: Optional[List[Dict[str, Any]]] = None, model_used: str = "gemini-3.6-flash") -> bool:
    """
    Adds a new calendar event extracted from emails, after verifying it doesn't already exist.
    Includes frontmatter metadata tags (ai_processed, ai_source, ai_model, ai_updated).
    """
    if existing_events:
        norm_new = normalize_title(summary)
        for existing in existing_events:
            ex_summary = existing.get('summary', '')
            ex_start = existing.get('start', {})
            ex_date = ex_start.get('date') or ex_start.get('dateTime', '')[:10]
            
            if ex_date == date_str and normalize_title(ex_summary) == norm_new:
                print(f"Skipping duplicate creation: '{summary}' on {date_str} already exists in calendar.")
                return False

    frontmatter = format_frontmatter(source="email", model=model_used)
    clean_body = description.strip() if description else "Automatically added from your email summary."
    full_description = frontmatter + clean_body

    event = {
        'summary': summary,
        'start': {'date': date_str},
        'end': {'date': date_str},
        'description': full_description,
        'reminders': {'useDefault': True}
    }
    try:
        service.events().insert(calendarId='primary', body=event).execute()
        print(f"Added Life Admin event: '{summary}' on {date_str}")
        return True
    except Exception as e:
        print(f"Error adding calendar event: {e}")
        return False
