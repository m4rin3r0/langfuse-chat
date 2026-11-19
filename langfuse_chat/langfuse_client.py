import json
import os
import requests
import urllib3
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
HOST       = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")


def _get(path:str, params:dict|None=None) -> dict:
    """Send an authenticated GET request to the Langfuse Public API.
    Args:
        path: API path relative to the host, e.g. "/api/public/traces".
        params: Optional query parameters to append to the request.
    Return:
        The parsed JSON response body.
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts (30 s).
        requests.JSONDecodeError: If the response body is not valid JSON.
    """
    response = requests.get(f"{HOST}{path}", auth=(PUBLIC_KEY, SECRET_KEY), params=params, timeout=30, verify=False)
    response.raise_for_status()
    return response.json()


def list_traces(limit:int=50, page:int=1) -> dict:
    """Fetch one page of traces from Langfuse.
    Args:
        limit: Maximum number of traces per page.
        page: 1-based page number to fetch.
    Return:
        The API response with the traces under "data" and pagination info under "meta".
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts.
    """
    return _get("/api/public/traces", params={"limit": limit, "page": page})


def list_trace_ids_by_model(model:str, trace_ids:list[str]) -> set[str]:
    """Fetch supplied trace IDs with generation observations using the given model.
    Args:
        model: Exact model name to match.
        trace_ids: Trace IDs to check.
    Return:
        Supplied trace IDs with at least one generation observation using model.
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If the API response lacks required fields.
    """
    matching_trace_ids = set()
    for offset in range(0, len(trace_ids), 100):
        query = {
            "view": "observations",
            "dimensions": [{"field": "traceId"}],
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "filters": [
                {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"},
                {"column": "providedModelName", "operator": "=", "value": model, "type": "string"},
                {"column": "traceId", "operator": "any of", "value": trace_ids[offset:offset + 100],
                 "type": "stringOptions"},
            ],
            "fromTimestamp": "2020-01-01T00:00:00.000Z",
            "toTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "config": {"row_limit": 100},
        }
        data = _get("/api/public/metrics", params={"query": json.dumps(query)})
        matching_trace_ids.update(row["traceId"] for row in data["data"] if row.get("traceId"))
    return matching_trace_ids


def list_models() -> list[str]:
    """Fetch distinct model names used by generation observations.
    Return:
        Sorted model names recorded in Langfuse traces.
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If the API response lacks required fields.
    """
    query = {
        "view": "observations",
        "dimensions": [{"field": "providedModelName"}],
        "metrics": [{"measure": "count", "aggregation": "count"}],
        "filters": [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "fromTimestamp": "2020-01-01T00:00:00.000Z",
        "toTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "config": {"row_limit": 1000},
    }
    data = _get("/api/public/metrics", params={"query": json.dumps(query)})
    return sorted({row["providedModelName"] for row in data["data"] if row.get("providedModelName")})


def list_agent_run_counts(trace_ids:list[str]) -> dict[str, int]:
    """Fetch non-judge AGENT observation counts for the supplied traces.
    Args:
        trace_ids: Trace IDs to count.
    Return:
        A mapping from trace ID to its number of non-judge agent runs.
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If the API response lacks required fields.
    """
    counts = {}
    for offset in range(0, len(trace_ids), 100):
        query = {
            "view": "observations",
            "dimensions": [{"field": "traceId"}],
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "filters": [
                {"column": "type", "operator": "=", "value": "AGENT", "type": "string"},
                {"column": "name", "operator": "does not contain", "value": "judge", "type": "string"},
                {"column": "traceId", "operator": "any of", "value": trace_ids[offset:offset + 100],
                 "type": "stringOptions"},
            ],
            "fromTimestamp": "2020-01-01T00:00:00.000Z",
            "toTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "config": {"row_limit": 100},
        }
        data = _get("/api/public/metrics", params={"query": json.dumps(query)})
        counts.update({row["traceId"]: row["count_count"] for row in data["data"] if row.get("traceId")})
    return counts


def get_trace_generation_summaries(trace_ids:list[str]) -> dict[str, tuple[str, int]]:
    """Fetch model names and total input/output tokens for generation observations.
    Args:
        trace_ids: Trace IDs to summarize.
    Return:
        A mapping from trace ID to its comma-separated model names and token total.
    Raises:
        requests.HTTPError: If the API responds with a 4xx/5xx status code.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If the API response lacks required fields.
    """
    models_by_trace = {}
    tokens_by_trace = {}
    for offset in range(0, len(trace_ids), 100):
        query = {
            "view": "observations",
            "dimensions": [{"field": "traceId"}, {"field": "providedModelName"}],
            "metrics": [
                {"measure": "inputTokens", "aggregation": "sum"},
                {"measure": "outputTokens", "aggregation": "sum"},
            ],
            "filters": [
                {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"},
                {"column": "traceId", "operator": "any of", "value": trace_ids[offset:offset + 100],
                 "type": "stringOptions"},
            ],
            "fromTimestamp": "2020-01-01T00:00:00.000Z",
            "toTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "config": {"row_limit": 1000},
        }
        data = _get("/api/public/metrics", params={"query": json.dumps(query)})
        for row in data["data"]:
            trace_id = row.get("traceId")
            if not trace_id:
                continue
            model = row.get("providedModelName")
            if model:
                models_by_trace.setdefault(trace_id, set()).add(model)
            tokens_by_trace[trace_id] = (
                tokens_by_trace.get(trace_id, 0)
                + int(row.get("sum_inputTokens") or 0)
                + int(row.get("sum_outputTokens") or 0)
            )
    return {
        trace_id: (", ".join(sorted(models_by_trace.get(trace_id, set()))) or "—",
                   tokens_by_trace.get(trace_id, 0))
        for trace_id in trace_ids
    }


def get_trace(trace_id:str) -> dict:
    """Fetch a single trace including all of its observations.
    Args:
        trace_id: ID of the trace to fetch.
    Return:
        The full trace as returned by the API, including the "observations" list.
    Raises:
        requests.HTTPError: If the trace does not exist (404) or the API returns another error status.
        requests.RequestException: On connection errors or timeouts.
    """
    return _get(f"/api/public/traces/{trace_id}")
