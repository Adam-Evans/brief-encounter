import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
import msal
import requests
import google.generativeai as genai

# Load configuration
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# MS Graph Config
CLIENT_ID = os.getenv("MS_CLIENT_ID")
# Client Secret isn't strictly needed for PublicClientApp but we'll keep it for the flow
TENANT_ID = os.getenv("MS_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Mail.Read", "Calendars.ReadWrite", "User.Read"]
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.bin"

# Gemini Config
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_ms_graph_token():
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text())

    # We use PublicClientApplication for personal accounts
    app = msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache
    )

    accounts = app.get_accounts()
    result = None

    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        print("Initial login or expired token. Starting Device Flow...")
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            TOKEN_CACHE_FILE.write_text(cache.serialize())
    
    return result.get("access_token")

def fetch_emails(token):
    headers = {"Authorization": f"Bearer {token}"}
    since = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    folders = ["inbox", "junkemail"]
    all_emails = []

    for folder in folders:
        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
        params = {
            "$filter": f"receivedDateTime ge {since}",
            "$select": "subject,from,receivedDateTime,bodyPreview,isRead",
            "$top": 50
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            emails = response.json().get("value", [])
            for e in emails:
                e["source_folder"] = folder
            all_emails.extend(emails)
    
    return all_emails

def create_calendar_event(token, event_data):
    url = "https://graph.microsoft.com/v1.0/me/calendar/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "subject": event_data["subject"],
        "start": {"dateTime": event_data["start"], "timeZone": "UTC"},
        "end": {"dateTime": event_data["end"], "timeZone": "UTC"},
        "body": {"contentType": "HTML", "content": "Automatically added from your email summary."}
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.status_code == 201

def summarize_and_process(token, emails):
    if not emails:
        return "No new emails to summarize."

    model = genai.GenerativeModel('gemini-3.6-flash')
    
    email_data = json.dumps([{
        "subject": e.get("subject"),
        "from": e.get("from", {}).get("emailAddress", {}).get("address"),
        "preview": e.get("bodyPreview"),
        "folder": e.get("source_folder")
    } for e in emails], indent=2)

    prompt = f"""
    You are an expert personal assistant. Analyze these emails from the last 24 hours.
    Reference Date: {datetime.date.today()}
    
    OUTPUT FORMAT:
    1. **Executive TL;DR**: 2-3 sentences max.
    2. **Important Emails**: List subjects and why they matter.
    3. **Junk Check**: 
       - List any emails in 'junkemail' that ARE NOT junk.
       - List any emails in 'inbox' that ARE junk.
    4. **Calendar Appointments**: If you find specific dates/times for meetings/events, extract them into a JSON block:
       ```json
       [
         {{
           "subject": "Title",
           "start": "YYYY-MM-DDTHH:MM:SS",
           "end": "YYYY-MM-DDTHH:MM:SS"
         }}
       ]
       ```
    
    EMAILS:
    {email_data}
    """
    
    response = model.generate_content(prompt)
    content = response.text
    
    if "```json" in content:
        try:
            json_str = content.split("```json")[1].split("```")[0].strip()
            events = json.loads(json_str)
            for event in events:
                if create_calendar_event(token, event):
                    print(f"Added to Calendar: {event['subject']}")
        except:
            pass
            
    return content

def main():
    print(f"--- Email Summarizer: {datetime.datetime.now()} ---")
    token = get_ms_graph_token()
    if not token:
        return

    emails = fetch_emails(token)
    print(f"Analyzing {len(emails)} emails...")
    
    summary = summarize_and_process(token, emails)
    
    output_path = BASE_DIR / f"summary_{datetime.date.today()}.md"
    output_path.write_text(summary)
    
    print("\n--- Summary Generated ---")
    print(summary)

if __name__ == "__main__":
    main()
