import os
import json
import datetime
import re
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
import time

# Load configuration
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Gmail & Calendar Config
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]
TOKEN_FILE = BASE_DIR / 'gmail_token.json'
CREDENTIALS_FILE = BASE_DIR / 'gmail_credentials.json'
TENNIS_LOG = BASE_DIR / 'data' / 'tennis_progress.json'

# Gemini Config
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def call_gemini_with_retry(contents, config=None):
    """
    Calls Gemini API using gemini-3.6-flash as primary, falling back to gemini-2.5-flash.
    Returns a tuple of (response_object, model_used_name).
    """
    models = ['gemini-3.6-flash', 'gemini-2.5-flash']
    for model_name in models:
        for attempt in range(4):
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return res, model_name
            except Exception as e:
                err_msg = str(e)
                print(f"Attempt {attempt+1} with {model_name} failed: {err_msg[:120]}...")
                time.sleep(10 * (attempt + 1))
    raise RuntimeError("Gemini model calls failed after retries.")

def parse_json_response(raw_text):
    """
    Safely parses JSON responses from Gemini, stripping markdown code blocks if present.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rfind("```") != -1:
            cleaned = cleaned[:cleaned.rfind("```")].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return json.loads(cleaned[start_idx:end_idx+1])
        raise

def normalize_title(title):
    """
    Normalizes event titles for fuzzy deduplication comparison.
    """
    if not title:
        return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def is_ai_processed(event):
    """
    Checks if a calendar event has frontmatter tags including ai_model tag.
    """
    desc = event.get('description', '')
    if not desc:
        return False
    return 'ai_processed: true' in desc and 'ai_model:' in desc

def deduplicate_calendar_events(service, events):
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

def get_google_services():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: {CREDENTIALS_FILE} not found.")
                return None, None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    return gmail, calendar

def tennis_coach_single(service, event):
    """
    Generates a progressive lesson plan for a tennis event and patches it with frontmatter tags.
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
    today_str = datetime.date.today().isoformat()
    frontmatter = f"---\nai_processed: true\nai_source: tennis_coach\nai_model: {model_used}\nai_updated: {today_str}\n---\n\n"
    
    if '--- AI LESSON PLAN ---' in desc:
        desc = desc.split('--- AI LESSON PLAN ---')[0].strip()
        
    new_plan = f"🎾 **Tennis Lesson Plan (Session {progress['last_lesson_index'] + 1})**\n\n{response.text.strip()}"
    updated_desc = frontmatter + (desc.strip() + "\n\n" if desc.strip() else "") + new_plan
    
    service.events().patch(calendarId='primary', eventId=event['id'], body={'description': updated_desc.strip()}).execute()
    print(f"Added tennis lesson plan to: {event['summary']}")
    
    progress['last_lesson_index'] += 1
    TENNIS_LOG.write_text(json.dumps(progress))

def enrich_untouched_calendar_events(calendar_service, events, emails):
    """
    Enriches calendar events that haven't been processed yet in a single batched API call
    to respect API rate limits and minimize token overhead.
    """
    untouched_events = [e for e in events if not is_ai_processed(e)]

    if not untouched_events:
        print("All upcoming calendar events have already been enriched with AI frontmatter.")
        return

    print(f"Enriching {len(untouched_events)} untouched calendar events in a single batch call...")
    today_str = datetime.date.today().isoformat()
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
                frontmatter = f"---\nai_processed: true\nai_source: calendar_insight\nai_model: {model_used}\nai_updated: {today_str}\n---\n\n"
                
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

def manage_drafts(service, replies_to_create):
    """
    1. Deletes drafts older than 7 days.
    2. Creates new drafts for specified emails (preventing duplicates for the same email).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    results = service.users().drafts().list(userId='me').execute()
    drafts = results.get('drafts', [])
    
    existing_draft_subjects = set()
    for d in drafts:
        draft = service.users().drafts().get(userId='me', id=d['id']).execute()
        msg_date = datetime.datetime.fromtimestamp(int(draft['message']['internalDate'])/1000, datetime.timezone.utc)
        if (now - msg_date).days >= 7:
            service.users().drafts().delete(userId='me', id=d['id']).execute()
            print(f"Deleted stale draft ID: {d['id']}")
        else:
            headers = draft.get('message', {}).get('payload', {}).get('headers', [])
            subj = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            if subj:
                existing_draft_subjects.add(subj.lower().strip())

    for reply in replies_to_create:
        expected_subj = f"Re: {reply['subject']}".lower().strip()
        if expected_subj in existing_draft_subjects:
            print(f"Skipping duplicate draft creation for: '{reply['subject']}'")
            continue

        try:
            from email.message import EmailMessage
            msg = EmailMessage()
            msg.set_content(reply['content'])
            msg['To'] = reply['to']
            msg['Subject'] = f"Re: {reply['subject']}"
            msg['In-Reply-To'] = reply['messageId']
            msg['References'] = reply['messageId']

            encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().drafts().create(userId='me', body={'message': {'raw': encoded_message}}).execute()
            print(f"Created smart draft for: {reply['subject']}")
            existing_draft_subjects.add(expected_subj)
        except Exception as e:
            print(f"Error creating draft: {e}")

def fetch_calendar_events(service):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    thirty_days_later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
    
    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=thirty_days_later,
        maxResults=50, singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

def add_calendar_event(service, summary, date_str, description="", existing_events=None, model_used="gemini-3.6-flash"):
    """
    Adds a new calendar event extracted from emails, after verifying it doesn't already exist.
    Includes frontmatter tags (ai_processed, ai_model, ai_source).
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

    today_str = datetime.date.today().isoformat()
    frontmatter = f"---\nai_processed: true\nai_source: email\nai_model: {model_used}\nai_updated: {today_str}\n---\n\n"
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

def send_summary_email(service, html_content):
    from email.message import EmailMessage
    user_email = os.getenv("USER_EMAIL")
    if not user_email:
        print("Error: USER_EMAIL environment variable is not set in .env")
        return
    
    msg = EmailMessage()
    msg['Subject'] = f"Your Daily Briefing - {datetime.date.today().strftime('%B %d')}"
    msg['From'] = 'me'
    msg['To'] = user_email
    msg.add_alternative(html_content, subtype='html')

    encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    create_message = {'raw': encoded_message}
    
    try:
        service.users().messages().send(userId="me", body=create_message).execute()
        print("Briefing email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

def get_email_body(payload):
    """
    Recursively extracts text content from Gmail API message payload.
    """
    body_text = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                try:
                    body_text += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                except Exception:
                    pass
            elif 'parts' in part:
                body_text += get_email_body(part)
    elif 'body' in payload and 'data' in payload['body']:
        try:
            body_text += base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        except Exception:
            pass
    return body_text

def fetch_emails_gmail(service):
    query = 'newer_than:1d'
    results = service.users().messages().list(userId='me', q=query, maxResults=50).execute()
    messages = results.get('messages', [])
    
    all_emails = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id']).execute()
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        
        full_text = get_email_body(msg.get('payload', {}))
        preview = full_text[:1500].strip() if full_text.strip() else msg.get('snippet', '')
        
        all_emails.append({"subject": subject, "from": sender, "preview": preview, "messageId": message['id']})
    
    return all_emails

def summarize_and_process(emails, calendar_events):
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

def main():
    print(f"--- Email Summarizer & Personal Coach 3.0: {datetime.datetime.now()} ---")
    
    gmail, calendar_service = get_google_services()
    if not gmail or not calendar_service:
        print("Failed to initialize Google services.")
        return

    # 1. Fetch upcoming calendar events
    events = fetch_calendar_events(calendar_service)
    print(f"Fetched {len(events)} upcoming calendar events.")
    
    # 2. Deduplicate existing calendar events
    events = deduplicate_calendar_events(calendar_service, events)
    
    # 3. Fetch recent emails (with full text body decoding)
    emails = fetch_emails_gmail(gmail)
    print(f"Fetched {len(emails)} recent emails.")
    
    # 4. Enrich untouched calendar events with insights, links & frontmatter tags (batched call)
    try:
        enrich_untouched_calendar_events(calendar_service, events, emails)
    except Exception as e:
        print(f"Skipping event enrichment due to temporary API rate limit / error: {e}")
    
    # Re-fetch events after enrichment so briefing reflects latest state
    events = fetch_calendar_events(calendar_service)
    
    # 5. Summarize emails, extract new events, and create smart drafts
    print(f"Analyzing {len(emails)} emails and {len(events)} events for Daily Briefing...")
    raw_response, main_model_used = summarize_and_process(emails, events)
    
    try:
        data = parse_json_response(raw_response)
        html_summary = data.get("html", "Error generating briefing.")
        
        # Add new calendar events (with deduplication check & frontmatter model tag)
        for event in data.get("new_calendar_events", []):
            summary = event.get('summary', '')
            date_str = event.get('date', '')
            desc = event.get('description', '')
            if summary and date_str:
                add_calendar_event(calendar_service, summary, date_str, description=desc, existing_events=events, model_used=main_model_used)
        
        # Manage smart drafts (with deduplication check)
        manage_drafts(gmail, data.get("smart_replies", []))
            
        # Send daily briefing email
        send_summary_email(gmail, html_summary)
    except Exception as e:
        print(f"Error processing Gemini response: {e}")
    
    print("Done.")

if __name__ == "__main__":
    main()
