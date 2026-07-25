import json
import datetime
from pathlib import Path
from typing import List, Dict, Any
from modules.ai_client import call_gemini_with_retry, parse_json_response
from modules.calendar_service import is_ai_processed, format_frontmatter

BASE_DIR = Path(__file__).parent.parent
TENNIS_LOG = BASE_DIR / 'data' / 'tennis_progress.json'

def tennis_coach_single(service: Any, event: Dict[str, Any]) -> None:
    """
    Generates a progressive lesson plan for a tennis event and patches it with frontmatter metadata.
    """
    if not TENNIS_LOG.exists():
        TENNIS_LOG.parent.mkdir(parents=True, exist_ok=True)
        progress = {"last_lesson_index": 0, "completed_skills": []}
    else:
        try:
            progress = json.loads(TENNIS_LOG.read_text())
        except Exception:
            progress = {"last_lesson_index": 0, "completed_skills": []}

    lesson_prompt = f"""
    Create a 60-minute tennis lesson plan for two beginners playing on a tarmac court.
    Context: They have completed {progress['last_lesson_index']} previous sessions.
    
    FORMATTING RULES:
    - Use clear, professional section headers.
    - Use bullet points for drills.
    - Keep it concise (phone-screen friendly).
    - Focus on tarmac safety and fun for beginners.
    
    STRUCTURE:
    🎾 WARM-UP (5 mins)
    👟 TECHNICAL DRILL (20 mins)
    🎾 PRACTICE RALLY (20 mins)
    🏆 FUN MINI-GAME (10 mins)
    🧘 COOL-DOWN (5 mins)
    """
    response, model_used = call_gemini_with_retry(contents=lesson_prompt)
    
    desc = event.get('description', '')
    frontmatter = format_frontmatter(source="tennis_coach", model=model_used)
    
    if '--- AI LESSON PLAN ---' in desc:
        desc = desc.split('--- AI LESSON PLAN ---')[0].strip()
        
    new_plan = f"🎾 **Tennis Lesson Plan (Session {progress['last_lesson_index'] + 1})**\n\n{response.text.strip()}"
    updated_desc = frontmatter + (desc.strip() + "\n\n" if desc.strip() else "") + new_plan
    
    service.events().patch(calendarId='primary', eventId=event['id'], body={'description': updated_desc.strip()}).execute()
    print(f"Added tennis lesson plan to: {event['summary']}")
    
    progress['last_lesson_index'] += 1
    TENNIS_LOG.write_text(json.dumps(progress))

def enrich_untouched_calendar_events(calendar_service: Any, events: List[Dict[str, Any]], emails: List[Dict[str, Any]]) -> None:
    """
    Enriches calendar events that haven't been processed yet in a single batched API call
    to respect API rate limits and minimize token overhead.
    """
    untouched_events = [e for e in events if not is_ai_processed(e)]

    if not untouched_events:
        print("All upcoming calendar events have already been enriched with AI frontmatter.")
        return

    print(f"Enriching {len(untouched_events)} untouched calendar events in a single batch call...")
    email_summaries = [{'subject': e['subject'], 'from': e['from'], 'preview': e['preview']} for e in emails[:15]]

    non_tennis_untouched = []
    for event in untouched_events:
        if 'tennis' in event.get('summary', '').lower():
            tennis_coach_single(calendar_service, event)
        else:
            non_tennis_untouched.append(event)

    if not non_tennis_untouched:
        return

    batch_input = []
    for e in non_tennis_untouched:
        batch_input.append({
            "id": e['id'],
            "summary": e.get('summary', ''),
            "start": e.get('start', {}),
            "current_description": e.get('description', '')
        })

    prompt = f"""
    You are an expert executive personal assistant and Life Admin concierge.
    Analyze these upcoming calendar events and enrich each with actionable insights, preparation steps, context, and direct web links.

    CALENDAR EVENTS TO ENRICH:
    {json.dumps(batch_input)}

    RECENT EMAILS (for reference if related):
    {json.dumps(email_summaries)}

    INSTRUCTIONS:
    1. Direct Official Web Links:
       - Provide direct, official web links for booking, tickets, official vendors, tracking, or locations where applicable (e.g. Colosseum tickets https://colosseo.it/en/opening-times-and-tickets/, Vatican Museums https://m.museivaticani.va/, courier tracking, hotel sites).
       - Format links in markdown: `[Link Title](https://...)`.
    2. Related Email Context:
       - Extract specific details (times, confirmation numbers, contact info) from recent emails if matching.
    3. Actionable Insights:
       - Provide concise, phone-friendly preparation checklists, tips, or reminders for each event.

    OUTPUT FORMAT:
    Return JSON object mapping each event ID to its enriched markdown insights:
    {{
      "enrichments": {{
        "event_id_1": "Markdown text with preparation steps, context, links...",
        "event_id_2": "..."
      }}
    }}
    """

    try:
        res, model_used = call_gemini_with_retry(
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        data = parse_json_response(res.text)
        enrichments = data.get("enrichments", {})

        for event in non_tennis_untouched:
            eid = event['id']
            insights = enrichments.get(eid, "")
            if insights:
                frontmatter = format_frontmatter(source="calendar_insight", model=model_used)
                
                clean_desc = event.get('description', '')
                if '---' in clean_desc and 'ai_processed:' in clean_desc:
                    parts = clean_desc.split('---')
                    if len(parts) >= 3:
                        clean_desc = '---'.join(parts[3:]).strip()

                new_desc = frontmatter + (clean_desc.strip() + "\n\n" if clean_desc.strip() else "") + "💡 **AI Insights & Links**\n" + insights.strip()
                
                calendar_service.events().patch(
                    calendarId='primary',
                    eventId=eid,
                    body={'description': new_desc.strip()}
                ).execute()
                print(f"Enriched calendar event: '{event.get('summary')}' (using {model_used})")
    except Exception as e:
        print(f"Error during batch event enrichment: {e}")
