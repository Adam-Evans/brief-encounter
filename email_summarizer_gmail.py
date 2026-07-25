#!/usr/bin/env python3
"""
Email Summarizer & Personal Coach 3.0
Main orchestration pipeline for email summarization, calendar deduplication, AI enrichment, and smart draft management.
"""

import datetime
from modules.ai_client import parse_json_response
from modules.auth import get_google_services
from modules.calendar_service import fetch_calendar_events, deduplicate_calendar_events, add_calendar_event
from modules.email_service import fetch_emails_gmail, manage_drafts, send_summary_email
from modules.enrichment import enrich_untouched_calendar_events
from modules.briefing import summarize_and_process

def main():
    print(f"--- Email Summarizer & Personal Coach 3.0: {datetime.datetime.now()} ---")
    
    # 1. Initialize Google API services
    gmail, calendar_service = get_google_services()
    if not gmail or not calendar_service:
        print("Failed to initialize Google services.")
        return

    # 2. Fetch & deduplicate upcoming calendar events
    events = fetch_calendar_events(calendar_service)
    print(f"Fetched {len(events)} upcoming calendar events.")
    events = deduplicate_calendar_events(calendar_service, events)
    
    # 3. Fetch recent emails with decoded body text
    emails = fetch_emails_gmail(gmail)
    print(f"Fetched {len(emails)} recent emails.")
    
    # 4. Enrich untouched calendar events (batched AI call with fail-safe guard)
    try:
        enrich_untouched_calendar_events(calendar_service, events, emails)
    except Exception as e:
        print(f"Skipping event enrichment due to temporary API rate limit / error: {e}")
    
    # Re-fetch events after enrichment so briefing reflects latest state
    events = fetch_calendar_events(calendar_service)
    
    # 5. Summarize emails, extract new events, and create smart drafts
    print(f"Analyzing {len(emails)} emails and {len(events)} events for Daily Briefing...")
    raw_response, main_model_used = summarize_and_process(emails, events)
    
    try:
        data = parse_json_response(raw_response)
        html_summary = data.get("html", "Error generating briefing.")
        
        # Add new calendar events (with deduplication check & frontmatter model tag)
        for event in data.get("new_calendar_events", []):
            summary = event.get('summary', '')
            date_str = event.get('date', '')
            desc = event.get('description', '')
            if summary and date_str:
                add_calendar_event(calendar_service, summary, date_str, description=desc, existing_events=events, model_used=main_model_used)
        
        # Manage smart drafts (with deduplication check)
        manage_drafts(gmail, data.get("smart_replies", []))
            
        # Send daily briefing email
        send_summary_email(gmail, html_summary)
    except Exception as e:
        print(f"Error processing Gemini response: {e}")
    
    print("Done.")

if __name__ == "__main__":
    main()
