import os
import json
import time
from typing import Tuple, Any, Dict, Optional
from dotenv import load_dotenv
from google import genai

# Ensure environment variables are loaded
load_dotenv()

_client: Optional[genai.Client] = None

def get_gemini_client() -> genai.Client:
    """
    Singleton getter for Gemini Client instance.
    """
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        _client = genai.Client(api_key=api_key)
    return _client

def call_gemini_with_retry(contents: Any, config: Optional[Dict[str, Any]] = None) -> Tuple[Any, str]:
    """
    Calls Gemini API using gemini-3.6-flash as primary, falling back to gemini-2.5-flash.
    Applies exponential backoff on 429 rate limits.
    Returns tuple of (response_object, model_name_used).
    """
    client = get_gemini_client()
    models = ['gemini-3.6-flash', 'gemini-2.5-flash']
    for model_name in models:
        for attempt in range(4):
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return res, model_name
            except Exception as e:
                err_msg = str(e)
                print(f"Attempt {attempt+1} with {model_name} failed: {err_msg[:120]}...")
                time.sleep(10 * (attempt + 1))
    raise RuntimeError("Gemini model calls failed after retries.")

def parse_json_response(raw_text: str) -> Dict[str, Any]:
    """
    Safely parses JSON responses from Gemini, stripping markdown code fences if present.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rfind("```") != -1:
            cleaned = cleaned[:cleaned.rfind("```")].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return json.loads(cleaned[start_idx:end_idx+1])
        raise
