import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.schema_parser import build_schema_catalog, collect_column_profile


class SchemaCatalogTest(unittest.TestCase):
    def test_build_schema_catalog_profiles_columns(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            db_path = Path(temp_dir) / "products.db"
            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE electric_vehicle("品牌" TEXT, "型号" TEXT, "档位数量" INTEGER)')
            conn.execute('INSERT INTO electric_vehicle VALUES ("雅迪", "天鹰T3", 3)')
            conn.execute('INSERT INTO electric_vehicle VALUES ("雅迪", "冠能", 5)')
            conn.commit()
            conn.close()

            catalog = build_schema_catalog(str(db_path), sample_limit=10)
            profile = collect_column_profile(str(db_path), "electric_vehicle", "档位数量")

        columns = catalog["tables"]["electric_vehicle"]["columns"]
        self.assertEqual(columns["品牌"]["role"], "brand")
        self.assertIn("雅迪", columns["品牌"]["enum_values"])
        self.assertEqual(columns["型号"]["role"], "model")
        self.assertEqual(profile["min_value"], 3.0)
        self.assertEqual(profile["max_value"], 5.0)


if __name__ == "__main__":
    unittest.main()

