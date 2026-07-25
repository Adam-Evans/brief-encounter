import os
import msal
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")
SCOPES = ["Mail.Read", "Calendars.ReadWrite", "User.Read"]
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.bin"

cache = msal.SerializableTokenCache()
app = msal.PublicClientApplication(
    CLIENT_ID, 
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    token_cache=cache
)

print("Starting Login Flow...")
flow = app.initiate_device_flow(scopes=SCOPES)
if "user_code" in flow:
    print(f"CODE: {flow["user_code"]}")
    print(f"MESSAGE: {flow["message"]}")
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        print("SUCCESS! Writing cache...")
        TOKEN_CACHE_FILE.write_text(cache.serialize())
    else:
        print(f"FAILED: {result.get("error_description")}")
else:
    print("Error initiating flow:", flow)
