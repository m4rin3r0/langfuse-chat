import json
from flask import Flask, render_template, abort, Response, request
from langfuse_client import (HOST, get_trace_generation_summaries, list_traces, list_trace_ids_by_model,
                             list_models, list_agent_run_counts, get_trace)
from parsing import build_chat, to_local, format_duration

MAX_TRACES = 1000
PAGE_SIZE  = 100

app = Flask(__name__)


def fetch_all_traces(limit_total:int=MAX_TRACES) -> list[dict]:
    """Fetch traces page by page until the limit or the last page is reached.
    Args:
        limit_total: Maximum total number of traces to return.
    Return:
        List of trace dicts in API order, at most limit_total entries.
    Raises:
        requests.HTTPError: If the Langfuse API returns an error status.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If the API response lacks the "data" or "meta" fields.
    """
    all_traces = []
    page = 1
    while len(all_traces) < limit_total:
        data  = list_traces(limit=PAGE_SIZE, page=page)
        items = data["data"]
        if not items:
            break
        all_traces.extend(items)
        if page >= data["meta"]["totalPages"]:
            break
        page += 1
    return all_traces[:limit_total]


@app.route("/")
def index():
    """Render the overview page with traces grouped by local day, optionally filtered by model.
    Args:
        None.
    Return:
        The rendered index.html with days sorted newest first.
    Raises:
        requests.HTTPError: If the Langfuse API returns an error status.
        requests.RequestException: On connection errors or timeouts.
        KeyError: If a trace lacks the "id" or "timestamp" field.
    """
    model_filter = request.args.get("model", "")
    search_query = request.args.get("search", "").strip()
    models = list_models()
    traces = fetch_all_traces()
    if model_filter:
        matching_trace_ids = list_trace_ids_by_model(model_filter, [trace["id"] for trace in traces])
        traces = [trace for trace in traces if trace["id"] in matching_trace_ids]
    if search_query:
        normalized_query = search_query.casefold()
        traces = [trace for trace in traces
                  if normalized_query in trace["id"].casefold()
                  or normalized_query in (trace.get("name") or "").casefold()]
    agent_run_counts = list_agent_run_counts([trace["id"] for trace in traces])
    generation_summaries = get_trace_generation_summaries([trace["id"] for trace in traces])
    traces.sort(key=lambda t: t["timestamp"], reverse=True)
    groups = {}
    for t in traces:
        local_dt = to_local(t["timestamp"])
        day_key  = local_dt.date().isoformat()
        llm, total_tokens = generation_summaries[t["id"]]
        groups.setdefault(day_key, []).append({"id": t["id"], "name": t.get("name") or "(unnamed)",
                                                "time": local_dt.strftime("%H:%M:%S"), "duration": format_duration(t.get("latency")),
                                                "agent_runs": agent_run_counts.get(t["id"], 0),
                                                "llm": llm, "total_tokens": f"{total_tokens:,}",
                                                "langfuse_url": f"{HOST}{t['htmlPath']}"})
    day_list = sorted(groups.items(), key=lambda kv: kv[0], reverse=True)
    return render_template("index.html", day_list=day_list, total=len(traces), model_filter=model_filter,
                           models=models, search_query=search_query)


@app.route("/trace/<trace_id>")
def trace_view(trace_id:str):
    """Render the chat view for a single trace.
    Args:
        trace_id: ID of the trace to display, taken from the URL.
    Return:
        The rendered trace.html with the trace header and chat turns.
    Raises:
        werkzeug.exceptions.NotFound: If the trace cannot be fetched (aborts with 404).
    """
    try:
        trace = get_trace(trace_id)
    except Exception:
        abort(404)
    header = {"name": trace.get("name"), "id": trace["id"], "time": to_local(trace["timestamp"]).strftime("%d.%m.%Y %H:%M:%S"),
              "duration": format_duration(trace.get("latency")), "langfuse_url": f"{HOST}{trace['htmlPath']}"}
    return render_template("trace.html", header=header, turns=build_chat(trace))


@app.route("/trace/<trace_id>/export")
def trace_export(trace_id:str):
    """Export a trace as a downloadable JSON file.
    Args:
        trace_id: ID of the trace to export, taken from the URL.
    Return:
        A JSON attachment response containing the raw trace plus the parsed chat under "chat".
    Raises:
        werkzeug.exceptions.NotFound: If the trace cannot be fetched (aborts with 404).
    """
    try:
        trace = get_trace(trace_id)
    except Exception:
        abort(404)
    # raw trace plus the parsed conversation, so tool IO is findable without matching duplicate observations
    payload = json.dumps({**trace, "chat": build_chat(trace)}, ensure_ascii=False, indent=2)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="trace_{trace_id}.json"'})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
