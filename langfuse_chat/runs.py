import csv
import io
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect_runs(database:str):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("""CREATE TABLE IF NOT EXISTS run_traces (
            run_id TEXT NOT NULL REFERENCES runs(id), trace_id TEXT NOT NULL,
            PRIMARY KEY (run_id, trace_id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS csv_upload (
            id INTEGER PRIMARY KEY CHECK (id = 1), filename TEXT NOT NULL)""")
        with connection:
            yield connection
    finally:
        connection.close()


def import_runs(database:str, content:bytes, filename:str|None=None) -> int:
    """Validate a UTF-8 CSV and atomically add its run/trace assignments."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("The CSV must use UTF-8 encoding.") from error
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    assignments = []
    names = {}
    try:
        if not reader.fieldnames or not {"run_id", "run_name", "trace_id"} <= set(reader.fieldnames):
            raise ValueError("Required CSV columns: run_id,run_name,trace_id.")
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV column names must be unique.")
        for row in reader:
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Line {line}: the number of fields does not match the header.")
            run_id, name, trace_id = (row[key].strip() for key in ("run_id", "run_name", "trace_id"))
            if not all((run_id, name, trace_id)):
                raise ValueError(f"Line {line}: run_id, run_name and trace_id must not be empty.")
            if run_id in names and names[run_id] != name:
                raise ValueError(f"Line {line}: conflicting names for run '{run_id}'.")
            names[run_id] = name
            assignments.append((run_id, trace_id))
    except csv.Error as error:
        raise ValueError(f"Line {reader.line_num}: invalid CSV ({error}).") from error
    if not assignments:
        raise ValueError("The CSV must contain at least one assignment.")
    with connect_runs(database) as connection:
        for run_id, name in names.items():
            existing = connection.execute("SELECT name FROM runs WHERE id = ?", (run_id,)).fetchone()
            if existing and existing[0] != name:
                raise ValueError(f"Run '{run_id}' already exists with a different name.")
            connection.execute("INSERT OR IGNORE INTO runs (id, name) VALUES (?, ?)", (run_id, name))
        before = connection.total_changes
        connection.executemany("INSERT OR IGNORE INTO run_traces (run_id, trace_id) VALUES (?, ?)", assignments)
        count = connection.total_changes - before
        if filename:
            connection.execute("INSERT OR REPLACE INTO csv_upload (id, filename) VALUES (1, ?)", (filename,))
        return count


def uploaded_csv_name(database:str) -> str|None:
    with connect_runs(database) as connection:
        row = connection.execute("SELECT filename FROM csv_upload WHERE id = 1").fetchone()
        return row[0] if row else None


def list_runs(database:str) -> list[tuple[str, str]]:
    with connect_runs(database) as connection:
        return connection.execute("SELECT id, name FROM runs ORDER BY name COLLATE NOCASE, id").fetchall()


def run_trace_ids(database:str, run_id:str) -> set[str]:
    with connect_runs(database) as connection:
        return {row[0] for row in connection.execute(
            "SELECT trace_id FROM run_traces WHERE run_id = ?", (run_id,))}
