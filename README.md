# Langfuse Chat

Displays Langfuse traces as a clean chat view (instead of the native Langfuse dashboard).

- All traces listed chronologically, grouped by day (newest first).
- Clicking a trace opens a chat view:
  - The LLM's reasoning texts and tool calls appear on the left.
  - Tool results (and the initial system/user message) appear on the right.
  - Below each message: duration and tokens used.

The setup is tailored to pydantic-ai traces (with `Agent.instrument_all()`), see `parsing.py`.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

## Running

```powershell
.venv\Scripts\python.exe langfuse_chat/app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Project Structure

- `langfuse_client.py` — REST client for the Langfuse Public API (Basic Auth with public/secret key).
- `parsing.py` — builds the chat turns from the raw trace observations (reasoning, tool calls, tool results, duration, tokens).
- `app.py` — Flask app with an overview page (`/`) and a chat view (`/trace/<id>`).
- `templates/`, `static/` — HTML templates and stylesheet.
