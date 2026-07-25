import os
import datetime
import base64
from typing import List, Dict, Any

def get_email_body(payload: Dict[str, Any]) -> str:
    """
    Recursively extracts plain text content from Gmail API message payload.
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

def fetch_emails_gmail(service: Any, query: str = 'newer_than:1d', max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches recent emails from Gmail API and extracts decoded plain-text body content.
    """
    results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    messages = results.get('messages', [])
    
    all_emails = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id']).execute()
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        
        full_text = get_email_body(msg.get('payload', {}))
        preview = full_text[:1500].strip() if full_text.strip() else msg.get('snippet', '')
        
        all_emails.append({"subject": subject, "from": sender, "preview": preview, "messageId": message['id']})
    
    return all_emails

def manage_drafts(service: Any, replies_to_create: List[Dict[str, Any]]) -> None:
    """
    1. Deletes drafts older than 7 days.
    2. Creates new smart drafts for specified emails, preventing duplicate drafts.
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

def send_summary_email(service: Any, html_content: str) -> None:
    """
    Sends the Daily Briefing HTML email to the configured USER_EMAIL address.
    """
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
