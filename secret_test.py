import os
import msal
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(".") / ".env")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

app = msal.ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

print("Attempting to get token via Client Secret...")
result = app.acquire_token_for_client(scopes=SCOPES)

if "access_token" in result:
    print("SUCCESS! Client Secret works.")
    print(f"Token (first 20 chars): {result['access_token'][:20]}...")
else:
    print(f"FAILED: {result.get('error')}")
    print(f"Description: {result.get('error_description')}")
