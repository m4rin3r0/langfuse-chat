# Langfuse Chat

Displays Langfuse traces as a clean chat view (instead of the native Langfuse dashboard).

- All traces listed chronologically, grouped by day (newest first).
- Clicking a trace opens a chat view:
  - The LLM's reasoning texts and tool calls appear on the left.
  - Tool results (and the initial system/user message) appear on the right.
  - Below each message: duration and tokens used.

The setup is tailored to pydantic-ai traces (with `Agent.instrument_all()`), see `parsing.py`.

## Setup

OrbAll commands are run from the repository root.

Create a `.env` file (see `.env.example`):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

For a self-hosted Langfuse instance, set `LANGFUSE_BASE_URL` to its URL, e.g. `http://localhost:3000`.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r langfuse_chat/requirements.txt
.venv/bin/python langfuse_chat/app.py
```

Or, with [uv](https://docs.astral.sh/uv/), in a single command without creating a venv first:

```bash
uv run --with-requirements langfuse_chat/requirements.txt langfuse_chat/app.py
```

> **Port 5000 already in use on macOS?** The AirPlay Receiver listens on port 5000. Turn it off under
> *System Settings → General → AirDrop & Handoff → AirPlay Receiver*, or change the port in `app.py`.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r langfuse_chat/requirements.txt
.venv\Scripts\python.exe langfuse_chat/app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Project Structure

- `langfuse_client.py` — REST client for the Langfuse Public API (Basic Auth with public/secret key).
- `parsing.py` — builds the chat turns from the raw trace observations (reasoning, tool calls, tool results, duration, tokens).
- `app.py` — Flask app with an overview page (`/`) and a chat view (`/trace/<id>`).
- `templates/`, `static/` — HTML templates and stylesheet.
