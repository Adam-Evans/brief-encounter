import os
import msal
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Mail.Read", "Calendars.ReadWrite", "User.Read"]
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.bin"
LOG_FILE = BASE_DIR / "auth_log.txt"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.ctime()}: {msg}\n")
    print(msg)

cache = msal.SerializableTokenCache()
app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

log("Starting background auth process...")
flow = app.initiate_device_flow(scopes=SCOPES)

# Write the code to a file so the user can see it if they miss the print
with open(BASE_DIR / "current_code.txt", "w") as f:
    f.write(f"CODE: {flow['user_code']}\n")
    f.write(f"MESSAGE: {flow['message']}\n")

log(f"CODE: {flow['user_code']}")
log("Waiting for user to authenticate...")

# This will poll until it succeeds or times out (default is 15-20 mins)
result = app.acquire_token_by_device_flow(flow)

if "access_token" in result:
    log("SUCCESS! Writing cache...")
    TOKEN_CACHE_FILE.write_text(cache.serialize())
    log("Cache written. You can now run the summarizer.")
else:
    log(f"FAILED: {result.get('error_description')}")
