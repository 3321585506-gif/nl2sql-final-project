import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.llm_client import LLMClient
from src.main import run_pipeline_with_context
from src.sql_checker import is_select_only, normalize_sql, validate_sql_schema
from src.sql_executor import execute_sql
from src.submission_writer import build_submission


class PipelineTest(unittest.TestCase):
    def test_sql_checker_blocks_dangerous_sql(self):
        self.assertTrue(is_select_only("SELECT * FROM air_conditioner;"))
        self.assertFalse(is_select_only("DELETE FROM air_conditioner;"))
        self.assertFalse(is_select_only("SELECT * FROM air_conditioner; DROP TABLE air_conditioner;"))

    def test_validate_sql_schema_accepts_known_table_and_column(self):
        schema = {
            "tables": {
                "air_conditioner": {
                    "columns": [
                        {"name": "brand", "type": "TEXT"},
                        {"name": "model", "type": "TEXT"},
                    ]
                }
            }
        }
        errors = validate_sql_schema("SELECT brand FROM air_conditioner;", schema)
        self.assertEqual(errors, [])

    def test_execute_sql_returns_structured_result(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            db_path = Path(temp_dir) / "products.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE air_conditioner(brand TEXT, model TEXT)")
            conn.execute("INSERT INTO air_conditioner VALUES ('g', 'm')")
            conn.commit()
            conn.close()

            result = execute_sql(str(db_path), "SELECT brand, model FROM air_conditioner;")
            self.assertTrue(result["success"])
            self.assertEqual(result["rows"], [{"brand": "g", "model": "m"}])

    def test_build_submission_uses_lantancy_field(self):
        submission = build_submission(
            "TEAM001",
            [{"id": "0", "query": "q", "predicted_sql": "SELECT 1;", "latency": 1.234}],
        )
        self.assertEqual(submission["results"][0]["lantancy"], "1.23s")

    def test_run_pipeline_with_context_writes_submission(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            test_file = Path(temp_dir) / "queries.jsonl"
            output_path = Path(temp_dir) / "predictions.json"
            test_file.write_text(
                json.dumps({"id": "0", "query": "list products"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            schema = {
                "tables": {
                    "air_conditioner": {
                        "columns": [
                            {"name": "brand", "type": "TEXT"},
                            {"name": "model", "type": "TEXT"},
                        ]
                    }
                }
            }

            run_pipeline_with_context(
                str(test_file),
                str(output_path),
                schema_info=schema,
                llm_client=LLMClient("mock", "mock"),
            )

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["team_id"], "TEAM001")
            self.assertEqual(data["results"][0]["predicted_sql"], normalize_sql("SELECT 1;"))


if __name__ == "__main__":
    unittest.main()
