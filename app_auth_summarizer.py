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
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
TENANT_ID = os.getenv("MS_TENANT_ID")
USER_EMAIL = os.getenv("USER_EMAIL")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

# Gemini Config
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_ms_graph_token():
    app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=SCOPES)
    if "access_token" in result:
        return result["access_token"]
    else:
        print(f"FAILED to get token: {result.get("error_description")}")
        return None

def fetch_emails(token):
    headers = {"Authorization": f"Bearer {token}"}
    since = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    folders = ["inbox", "junkemail"]
    all_emails = []

    for folder in folders:
        url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/mailFolders/{folder}/messages"
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
        else:
            print(f"Error fetching {folder}: {response.status_code} - {response.text}")
    
    return all_emails

def create_calendar_event(token, event_data):
    url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/calendar/events"
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

    model = genai.GenerativeModel("gemini-1.5-flash")
    
    email_data = json.dumps([{
        "subject": e.get("subject"),
        "from": e.get("from", {}).get("emailAddress", {}).get("address"),
        "preview": e.get("bodyPreview"),
        "folder": e.get("source_folder")
    } for e in emails], indent=2)

    prompt = f"Summarize these emails: {email_data}"
    
    response = model.generate_content(prompt)
    content = response.text
    return content

def main():
    print(f"--- Email Summarizer: {datetime.datetime.now()} ---")
    token = get_ms_graph_token()
    if not token:
        return

    emails = fetch_emails(token)
    print(f"Analyzing {len(emails)} emails...")
    
    summary = summarize_and_process(token, emails)
    print(summary)

if __name__ == "__main__":
    main()
