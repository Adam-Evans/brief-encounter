import imaplib
import email
from email.header import decode_header
import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load configuration
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# IMAP Config
IMAP_SERVER = "outlook.office365.com"
IMAP_USER = os.getenv("USER_EMAIL")
IMAP_PASS = os.getenv("EMAIL_PASS") # Should be an App Password

# Gemini Config
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def fetch_emails_imap():
    try:
        # Connect to server
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USER, IMAP_PASS)
        
        # Search for emails in the last 24 hours
        mail.select("inbox")
        date = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%d-%b-%Y")
        _, search_data = mail.search(None, f'(SINCE "{date}")')
        
        email_ids = search_data[0].split()
        all_emails = []

        print(f"Found {len(email_ids)} emails since {date}")

        for e_id in email_ids[-50:]: # Process last 50 emails
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Decode subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    # Decode from
                    from_ = msg.get("From")
                    
                    # Get body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    all_emails.append({
                        "subject": subject,
                        "from": from_,
                        "preview": body[:200].replace("\n", " ").strip(),
                        "folder": "inbox"
                    })
        
        mail.logout()
        return all_emails
    except Exception as e:
        print(f"IMAP Error: {e}")
        return []

def summarize_and_process(emails):
    if not emails:
        return "No new emails to summarize."

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    email_data = json.dumps(emails, indent=2)

    prompt = f"""
    You are an expert personal assistant. Analyze these emails from the last 24 hours.
    Reference Date: {datetime.date.today()}
    
    OUTPUT FORMAT:
    1. **Executive TL;DR**: 2-3 sentences max.
    2. **Important Emails**: List subjects and why they matter.
    3. **Action Items**: List any tasks or follow-ups extracted from these emails.
    
    EMAILS:
    {email_data}
    """
    
    response = model.generate_content(prompt)
    return response.text

def main():
    print(f"--- Email Summarizer (IMAP): {datetime.datetime.now()} ---")
    
    if not IMAP_USER or not IMAP_PASS:
        print("Error: USER_EMAIL and EMAIL_PASS must be set in .env")
        return

    emails = fetch_emails_imap()
    print(f"Analyzing {len(emails)} emails...")
    
    summary = summarize_and_process(emails)
    
    output_path = BASE_DIR / f"summary_imap_{datetime.date.today()}.md"
    output_path.write_text(summary)
    
    print("\n--- Summary Generated ---")
    print(summary)

if __name__ == "__main__":
    main()
