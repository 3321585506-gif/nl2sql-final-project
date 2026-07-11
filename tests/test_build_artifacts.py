import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.build_artifacts import ARTIFACT_FILES, build_all_artifacts, load_runtime_artifacts


class BuildArtifactsTest(unittest.TestCase):
    def test_build_and_load_runtime_artifacts(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            db_path = root / "products.db"
            out_dir = root / "processed"

            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE electric_vehicle("品牌" TEXT, "型号" TEXT, "车架材质" TEXT)')
            conn.execute('INSERT INTO electric_vehicle VALUES ("雅迪", "天鹰T3", "铝合金")')
            conn.commit()
            conn.close()

            build_all_artifacts(str(db_path), str(out_dir))
            artifacts = load_runtime_artifacts(str(out_dir))
            artifact_names = {path.name for path in out_dir.iterdir()}

            for filename in ARTIFACT_FILES.values():
                self.assertIn(filename, artifact_names)
        self.assertIn("schema_catalog", artifacts)
        self.assertIn("value_index", artifacts)
        self.assertIn("entity_indexes", artifacts)
        self.assertIn("schema_graph", artifacts)
        self.assertIn("铝合金", artifacts["value_index"])


if __name__ == "__main__":
    unittest.main()
