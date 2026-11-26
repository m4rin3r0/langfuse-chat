import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "langfuse_chat"))

import app as app_module
from runs import import_runs, list_runs, run_trace_ids, uploaded_csv_name


class RunImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / "runs.sqlite3")

    def test_persistent_additive_assignments(self):
        content = b"\xef\xbb\xbfrun_id,run_name,trace_id\r\nr1,Baseline,t1\r\nr1,Baseline,t1\r\nr2,Experiment,t1\r\n"
        self.assertEqual(import_runs(self.database, content), 2)
        self.assertEqual(import_runs(self.database, content), 0)
        self.assertEqual(run_trace_ids(self.database, "r1"), {"t1"})
        self.assertEqual(run_trace_ids(self.database, "r2"), {"t1"})
        self.assertEqual(list_runs(self.database), [("r1", "Baseline"), ("r2", "Experiment")])

    def test_invalid_csv_does_not_save_partial_import(self):
        for content in (
            b"run_id,run_name\nr1,Baseline\n",
            b"run_id,run_name,trace_id\nr1,Baseline,t1\nr1,Baseline,\n",
            b"run_id,run_name,trace_id\nr1,Baseline,t1\nr1,Other,t2\n",
            b'run_id,run_name,trace_id\nr1,"unterminated,t1',
            b"run_id,run_name,trace_id\nr1,\xff,t1\n",
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                import_runs(self.database, content)
            self.assertEqual(list_runs(self.database), [])

    def test_conflict_with_saved_run_rolls_back(self):
        import_runs(self.database, b"run_id,run_name,trace_id\nr1,Baseline,t1\n")
        with self.assertRaises(ValueError):
            import_runs(self.database, b"run_id,run_name,trace_id\nr2,New,t2\nr1,Other,t3\n")
        self.assertEqual(list_runs(self.database), [("r1", "Baseline")])
        self.assertEqual(run_trace_ids(self.database, "r1"), {"t1"})

    def test_upload_and_combined_filters(self):
        with patch.dict(app_module.app.config, RUNS_DATABASE=self.database, TESTING=True):
            client = app_module.app.test_client()
            response = client.post("/runs/import", data={
                "file": (io.BytesIO(b"run_id,run_name,trace_id\nr1,Baseline,t1\n"), "runs.csv")})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"1 new assignments", response.data)
            self.assertEqual(uploaded_csv_name(self.database), "runs.csv")
            traces = [
                {"id": trace_id, "name": "Example", "timestamp": "2026-11-26T09:00:00Z",
                 "htmlPath": "/project/p/traces/" + trace_id}
                for trace_id in ("t1", "t2")
            ]
            with (
                patch.object(app_module, "fetch_all_traces", return_value=traces),
                patch.object(app_module, "list_models", return_value=["model-a"]),
                patch.object(app_module, "list_trace_ids_by_model", return_value={"t1", "t2"}),
                patch.object(app_module, "list_agent_run_counts", return_value={}),
                patch.object(app_module, "get_trace_generation_summaries",
                             return_value={"t1": ("model-a", 5)}),
            ):
                response = client.get("/?run=r1&model=model-a&search=Example")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'href="/trace/t1"', response.data)
            self.assertNotIn(b'href="/trace/t2"', response.data)
            self.assertIn(b'Run', response.data)
            self.assertIn(b'name="run" value="r1"', response.data)
            self.assertIn(b"uploaded: runs.csv", response.data)
            self.assertNotIn(b'type="file"', response.data)
            self.assertIn(b'disabled>Upload CSV', response.data)
            response = client.post("/runs/import", data={
                "file": (io.BytesIO(b"invalid"), "runs.csv")})
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"No assignments were imported", response.data)
            self.assertEqual(uploaded_csv_name(self.database), "runs.csv")

    def test_failed_first_upload_keeps_picker_available(self):
        with patch.dict(app_module.app.config, RUNS_DATABASE=self.database, TESTING=True):
            client = app_module.app.test_client()
            response = client.post("/runs/import", data={
                "file": (io.BytesIO(b"invalid"), "bad.csv")})
            self.assertEqual(response.status_code, 400)
            self.assertIsNone(uploaded_csv_name(self.database))
            with (
                patch.object(app_module, "fetch_all_traces", return_value=[]),
                patch.object(app_module, "list_models", return_value=[]),
                patch.object(app_module, "list_agent_run_counts", return_value={}),
                patch.object(app_module, "get_trace_generation_summaries", return_value={}),
            ):
                response = client.get("/")
            self.assertIn(b'type="file"', response.data)
            self.assertNotIn(b'disabled>Upload CSV', response.data)


if __name__ == "__main__":
    unittest.main()
