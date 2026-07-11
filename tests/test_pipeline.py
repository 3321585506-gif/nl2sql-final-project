import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import config
from src.llm_client import LLMClient
from src.main import run_pipeline_with_context
from src.sql_checker import is_select_only, normalize_sql, validate_sql_schema
from src.sql_executor import execute_sql
from src.sql_generator import generate_sql_for_question
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
            self.assertEqual(data["team_id"], config.TEAM_ID)
            self.assertEqual(data["results"][0]["predicted_sql"], normalize_sql("SELECT 1;"))

    def test_generate_sql_rule_route_keeps_legacy_fields(self):
        schema = {
            "tables": {
                "electric_vehicle": {
                    "columns": [
                        {"name": "品牌", "type": "TEXT", "sample_values": ["雅迪"]},
                        {"name": "型号", "type": "TEXT", "sample_values": ["天鹰T3"]},
                        {"name": "车架材质", "type": "TEXT", "sample_values": ["铝合金"]},
                    ]
                }
            }
        }
        indexes = {
            "alias_map": {
                "品牌": [{"table": "electric_vehicle", "field": "品牌", "type": "TEXT"}],
                "型号": [{"table": "electric_vehicle", "field": "型号", "type": "TEXT"}],
                "车架材质": [{"table": "electric_vehicle", "field": "车架材质", "type": "TEXT"}],
            },
            "inverted_index": {},
            "top_k_fields": 10,
        }

        result = generate_sql_for_question(
            "车架材质是铝合金的电动车品牌和型号",
            schema,
            indexes,
            graph={},
            llm_client=LLMClient("mock", "mock"),
        )

        self.assertEqual(result["route"], "rule")
        self.assertIn("predicted_sql", result)
        self.assertIn("latency", result)
        self.assertIn("stage_timings", result)
        self.assertIn("车架材质 = '铝合金'", result["predicted_sql"])


if __name__ == "__main__":
    unittest.main()
