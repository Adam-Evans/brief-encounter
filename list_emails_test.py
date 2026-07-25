import os
import requests
import msal
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(".") / ".env")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
USER_EMAIL = os.getenv("USER_EMAIL")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

app = msal.ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

result = app.acquire_token_for_client(scopes=SCOPES)

if "access_token" in result:
    token = result["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # For Application permissions, we use /users/{id}/messages
    url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/messages"
    params = {"$top": 1, "$select": "subject"}
    
    print(f"Attempting to fetch emails for {USER_EMAIL}...")
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        print("SUCCESS! Can read emails.")
        messages = response.json().get("value", [])
        if messages:
            print(f"Latest email subject: {messages[0]['subject']}")
        else:
            print("No emails found, but API call succeeded.")
    else:
        print(f"FAILED to read emails. Status: {response.status_code}")
        print(response.text)
else:
    print("FAILED to get token.")
