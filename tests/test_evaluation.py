import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.evaluation import evaluate_predictions


class EvaluationTest(unittest.TestCase):
    def test_validation_records_without_id_align_from_one(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "products.db"
            pred_path = temp_path / "predictions.json"
            gold_path = temp_path / "validation.jsonl"

            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE product(name TEXT)")
            conn.execute("INSERT INTO product VALUES ('a')")
            conn.commit()
            conn.close()

            pred_path.write_text(
                json.dumps(
                    {
                        "team_id": "T",
                        "results": [
                            {
                                "id": "Q0001",
                                "query": "q",
                                "predicted_sql": "SELECT name FROM product;",
                                "lantancy": "0.01s",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            gold_path.write_text(
                json.dumps({"query": "q", "sql": "SELECT name FROM product"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = evaluate_predictions(str(pred_path), str(gold_path), str(db_path))

        self.assertEqual(result["total_samples"], 1)
        self.assertEqual(result["exec_match"], 1.0)


if __name__ == "__main__":
    unittest.main()

