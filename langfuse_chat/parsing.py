import json
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Berlin")


def to_local(iso_ts:str) -> datetime:
    """Convert an ISO 8601 timestamp to a datetime in the local time zone.
    Args:
        iso_ts: ISO 8601 timestamp, optionally with a trailing "Z" for UTC.
    Return:
        Timezone-aware datetime in LOCAL_TZ (Europe/Berlin).
    Raises:
        ValueError: If iso_ts is not a valid ISO 8601 timestamp.
    """
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return dt.astimezone(LOCAL_TZ)


def format_duration(seconds:float|None) -> str|None:
    """Format a duration in seconds as a short human-readable string.
    Args:
        seconds: Duration in seconds, or None.
    Return:
        "123 ms" below one second, "12.3 s" below one minute, otherwise "2m 5s";
        None if seconds is None or 0.
    Raises:
        None.
    """
    if not seconds:
        return None
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)}m {secs:.0f}s"


def format_tokens(prompt:int, completion:int, total:int) -> str|None:
    """Format token counts as "<in> in / <out> out / <total> total".
    Args:
        prompt: Number of prompt (input) tokens.
        completion: Number of completion (output) tokens.
        total: Total number of tokens.
    Return:
        The formatted string with "." as thousands separator, or None if total is 0.
    Raises:
        None.
    """
    if not total:
        return None
    return f"{prompt:,} in / {completion:,} out / {total:,} total".replace(",", ".")


def _pretty(value) -> str:
    """Pretty-print a value as indented JSON, parsing JSON strings first.
    Args:
        value: Any JSON-serializable value or a string that may contain JSON.
    Return:
        Indented JSON, or the original string if it is not valid JSON.
    Raises:
        TypeError: If value (after parsing) is not JSON-serializable.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return json.dumps(value, indent=2, ensure_ascii=False)


def _scope_name(obs:dict) -> str|None:
    """Read the instrumentation scope name from an observation's metadata.
    Args:
        obs: A Langfuse observation dict.
    Return:
        The value of metadata.scope.name (e.g. "pydantic-ai"), or None if missing.
    Raises:
        None.
    """
    return ((obs.get("metadata") or {}).get("scope") or {}).get("name")


def _seed_turns(generations:list[dict]) -> list[dict]:
    """Build the initial system/user turns from the first generation's input.
    Args:
        generations: Generation observations sorted by start time.
    Return:
        List of right-side turns for each system/user message; empty if there are no generations.
    Raises:
        KeyError: If a message lacks the "role" field.
        AttributeError: If the input messages or parts are not dicts.
    """
    if not generations:
        return []
    turns = []
    for msg in (generations[0].get("input") or {}).get("messages", []):
        if msg.get("role") not in ("system", "user"):
            continue
        text = "\n\n".join(p.get("content", "") for p in msg.get("parts", []) if p.get("type") == "text")
        turns.append({"side": "right", "kind": msg["role"], "label": "System" if msg["role"] == "system" else "User",
                      "blocks": [{"type": "text", "text": text}], "duration": None, "tokens": None, "time": None})
    return turns


def _assistant_turn(obs:dict) -> list[dict]:
    """Build left-side assistant turns from a generation's output.
    Args:
        obs: A generation observation whose output is a list of messages.
    Return:
        One turn per assistant message with thinking, tool-call and text blocks,
        plus duration, tokens and start time.
    Raises:
        AttributeError: If the output messages or parts are not dicts.
        TypeError: If tool-call arguments are not JSON-serializable.
    """
    turns = []
    for msg in (obs.get("output") or []):
        if msg.get("role") != "assistant":
            continue
        blocks = []
        for part in msg.get("parts", []):
            if part.get("type") == "thinking":
                blocks.append({"type": "thinking", "text": part.get("content", "")})
            elif part.get("type") == "tool_call":
                blocks.append({"type": "tool_call", "text": f"{part.get('name')}({_pretty(part.get('arguments'))})"})
            elif part.get("type") == "text":
                blocks.append({"type": "text", "text": part.get("content", "")})
        turns.append({"side": "left", "kind": "assistant", "label": "Assistant", "blocks": blocks,
                      "duration": format_duration(obs.get("latency")),
                      "tokens": format_tokens(obs.get("promptTokens", 0), obs.get("completionTokens", 0), obs.get("totalTokens", 0)),
                      "time": obs.get("startTime")})
    return turns


def _tool_turn(obs:dict) -> dict:
    """Build a right-side turn from a tool observation.
    Args:
        obs: A tool observation with optional input and an output.
    Return:
        A turn with the tool input (if present) and result blocks, plus duration and start time.
    Raises:
        TypeError: If the tool input or output is not JSON-serializable.
    """
    blocks = []
    if obs.get("input") is not None:
        blocks.append({"type": "tool_input", "text": _pretty(obs.get("input"))})
    blocks.append({"type": "tool_result", "text": _pretty(obs.get("output"))})
    return {"side": "right", "kind": "tool", "label": obs.get("name") or "Tool", "blocks": blocks,
            "duration": format_duration(obs.get("latency")), "tokens": None, "time": obs.get("startTime")}


def build_chat(trace:dict) -> list[dict]:
    """Convert a trace's pydantic-ai observations into a chronological list of chat turns.
    Args:
        trace: A full trace dict including its "observations" list.
    Return:
        Chat turns: initial system/user messages followed by assistant and tool turns ordered by start time.
    Raises:
        KeyError: If a relevant observation lacks the "startTime" field.
    """
    observations = trace.get("observations") or []
    generations  = sorted((o for o in observations if o.get("type") == "GENERATION" and _scope_name(o) == "pydantic-ai"), key=lambda o: o["startTime"])
    tool_results = [o for o in observations if o.get("type") == "TOOL" and _scope_name(o) == "pydantic-ai" and o.get("output") is not None]
    events = sorted([("gen", o) for o in generations] + [("tool", o) for o in tool_results], key=lambda e: e[1]["startTime"])
    turns = _seed_turns(generations)
    for kind, obs in events:
        turns.extend(_assistant_turn(obs) if kind == "gen" else [_tool_turn(obs)])
    return turns
