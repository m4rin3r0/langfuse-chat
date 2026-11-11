import os
import requests
import urllib3
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
