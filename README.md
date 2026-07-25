# 📬 Brief Encounter

> An intelligent, executive personal assistant & Life Admin concierge powered by **Gemini 3.6 Flash**.  
> Automatically turns your inbox into an actionable schedule, enriches calendar events with official vendor links & prep checklists, removes duplicate entries, and dispatches daily executive HTML briefings.

---

## ✨ Key Features

- **⚡ Gemini 3.6 Flash Integration**: Powered by the latest Gemini model with intelligent rate-limit backoff.
- **📅 Smart Calendar Deduplication**: Automatically scans Google Calendar and cleans up duplicate entries based on normalized titles and start dates.
- **💡 Rich AI Insights & Official Vendor Links**: Enriches calendar events with actionable checklists and direct official booking/tracking links (e.g. Colosseum tickets, Vatican Museums, package tracking, hotel portals, sports prep).
- **🏷️ Metadata Frontmatter Tags**: Attaches YAML frontmatter (`ai_processed`, `ai_model`, `ai_source`, `ai_updated`) to ensure 100% idempotent runs without re-enriching touched events.
- **✉️ Full Email Decoding & Smart Drafts**: Extracts full plain-text email bodies (up to 1,500 characters) and creates deduplicated response drafts in Gmail.
- **📧 Daily HTML Executive Briefing**: Dispatches a dark-themed daily briefing email summarizing your TL;DR, Life Admin highlights, draft replies, and a 30-day look-ahead.

---

## 🏗️ Project Architecture

```text
brief-encounter/
├── email_summarizer_gmail.py       # Main pipeline entrypoint script
├── modules/
│   ├── ai_client.py                 # Gemini API client, retries, backoff, JSON parsing
│   ├── auth.py                      # Google OAuth credential handling & service initialization
│   ├── calendar_service.py          # Deduplication, title normalization, frontmatter formatting
│   ├── email_service.py             # MIME body decoding, Gmail fetch, smart draft deduplication
│   ├── enrichment.py                # Batched AI event insights & official vendor links
│   └── briefing.py                  # Executive briefing prompt & HTML generator
└── tests/                           # Unit test suite
    ├── test_calendar.py             # Unit tests for title normalization & frontmatter parsing
    └── test_ai_client.py            # Unit tests for JSON parsing
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- Google Cloud Project with Gmail API & Google Calendar API enabled
- Gemini API Key

### 2. Environment Setup
Copy the configuration templates:
```bash
cp .env.example .env
cp gmail_credentials.json.example gmail_credentials.json
```
Populate `.env` with your `GEMINI_API_KEY` and `USER_EMAIL`. Place your OAuth desktop credentials in `gmail_credentials.json`.

### 3. Running the Pipeline
```bash
python3 email_summarizer_gmail.py
```

### 4. Running Unit Tests
```bash
python3 -m unittest discover tests
```

---

## 📜 License

MIT License.
