import os
import msal
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Mail.Read", "Calendars.ReadWrite", "User.Read"]
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.bin"

cache = msal.SerializableTokenCache()

# Force the app to treat itself as a Public Client to allow Device Flow
# while still providing the Secret that Azure is demanding.
app = msal.PublicClientApplication(
    CLIENT_ID, 
    authority=AUTHORITY, 
    client_credential=CLIENT_SECRET, 
    token_cache=cache
)

print("Starting Login Flow...")
flow = app.initiate_device_flow(scopes=SCOPES)
print(f"CODE: {flow['user_code']}")
print(f"MESSAGE: {flow['message']}")

result = app.acquire_token_by_device_flow(flow)

if "access_token" in result:
    print("SUCCESS! Writing cache...")
    TOKEN_CACHE_FILE.write_text(cache.serialize())
else:
    print(f"FAILED: {result.get('error_description')}")
