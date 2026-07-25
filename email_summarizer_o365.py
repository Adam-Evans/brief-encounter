import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
from O365 import Account, FileSystemTokenBackend
import google.generativeai as genai

# Load configuration
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# O365 / Microsoft Graph Config
# Using a well-known Public Client ID for CLI applications
CLIENT_ID = '04b07795-8ddb-461a-bbee-02f9e1bf7b46' 
# Use FileSystemTokenBackend to store refresh tokens locally
TOKEN_BACKEND = FileSystemTokenBackend(token_path=BASE_DIR, token_filename='o365_token.txt')

# Gemini Config
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_o365_account():
    # For public flow, O365 expects just the client_id string
    credentials = CLIENT_ID
    # Explicitly set auth_flow_type to 'public' and tenant_id to 'common' for personal accounts
    account = Account(credentials, token_backend=TOKEN_BACKEND, auth_flow_type='public', tenant_id='common')
    
    if not account.is_authenticated:
        # Use Device Code Flow
        scopes = ['https://graph.microsoft.com/Mail.Read']
        
        # We need to access the underlying connection to trigger device flow
        con = account.con
        # MSAL PublicClientApplication is used under the hood
        app = con.msal_client
        
        flow = app.initiate_device_flow(scopes=scopes)
        if 'user_code' not in flow:
            raise ValueError(f"Fail to create device flow. Error: {flow.get('error_description')}")
            
        print(f"--- ACTION REQUIRED ---")
        print(flow['message'])
        
        # Block until authenticated
        result = app.acquire_token_by_device_flow(flow)
        
        if 'access_token' in result:
            # Manually load the token into the account
            con.token_backend.save_token(result)
            account.is_authenticated = True
            print("Authentication successful!")
        else:
            print(f"Authentication failed: {result.get('error_description')}")
    
    return account

def fetch_emails_o365(account):
    mailbox = account.mailbox()
    
    # Get emails from the last 24 hours
    since = datetime.datetime.now() - datetime.timedelta(days=1)
    query = mailbox.new_query().on_attribute('receivedDateTime').greater_equal(since)
    
    messages = mailbox.get_messages(limit=50, query=query, download_attachments=False)
    
    all_emails = []
    for msg in messages:
        all_emails.append({
            "subject": msg.subject,
            "from": msg.sender.address,
            "preview": msg.body_preview,
            "received": msg.received.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return all_emails

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
    print(f"--- Email Summarizer (O365): {datetime.datetime.now()} ---")
    
    account = get_o365_account()
    
    if not account.is_authenticated:
        # We need to handle the token request step manually for the first run
        # This part will be interactive for the user
        print("Please follow the instructions above to authenticate.")
        return

    emails = fetch_emails_o365(account)
    print(f"Analyzing {len(emails)} emails...")
    
    summary = summarize_and_process(emails)
    
    output_path = BASE_DIR / f"summary_o365_{datetime.date.today()}.md"
    output_path.write_text(summary)
    
    print("\n--- Summary Generated ---")
    print(summary)

if __name__ == "__main__":
    main()
