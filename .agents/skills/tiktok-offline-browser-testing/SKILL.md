---
name: tiktok-offline-browser-testing
description: Run isolated offline browser checks for TikTok Travel Saver without API calls or persistent seed mutations.
---

# Offline browser testing

Use the repository's core virtualenv dependencies (`requirements.txt`) for UI
testing. Do not install extraction dependencies for the offline missing-dependency
error scenario; verify the startup banner says extraction is disabled.

Start from the repository root with a fresh throwaway store:

```bash
source .venv/bin/activate
SUPABASE_URL= SUPABASE_SERVICE_ROLE_KEY= GOOGLE_API_KEY= ASSEMBLYAI_API_KEY= \
  LIBRARY_FILE=$(mktemp -d)/library.json PORT=5050 python3 -u web_viewer.py
```

Set the keys to empty strings rather than unsetting them: `load_dotenv` does not
override variables already present, so a local `.env` cannot reintroduce them
(`env -u` would not protect against that). Never overwrite `.env` or print its
values. Confirm startup says `Library backend: local` before mutating
trips/statuses. Restart after template edits; templates load
at import time.

The header Create trip action opens the New trip sheet. Select a country before
typing a city. Typeahead focus may immediately open suggestions. Escape first
dismisses suggestions, then closes the sheet. Global n is suppressed while an
input is focused; Escape from search clears and blurs it before using n.

Use a full fake TikTok URL for offline /add failure checks, not a short URL
requiring external resolution. Missing dependencies and missing keys are different
error paths, so record the actual dependency state.

After approval/undo, reload the detail and revisit home/trip pages rather than
relying on already-rendered history state.

Check actual screenshots for emoji rendering and sticky-header anchor overlap;
DOM flag text alone does not establish visible flag rendering.

## Devin Secrets Needed

None for offline browse/create/approve/undo and missing-dependency failure testing.
Live extraction is a separate scope requiring GOOGLE_API_KEY and
ASSEMBLYAI_API_KEY plus extraction dependencies.
