import unittest

from src.index_builder import build_entity_indexes, build_value_index


class IndexBuilderTest(unittest.TestCase):
    def test_build_value_and_entity_indexes(self):
        catalog = {
            "tables": {
                "electric_vehicle": {
                    "columns": {
                        "品牌": {
                            "role": "brand",
                            "sample_values": ["雅迪"],
                            "enum_values": ["雅迪"],
                        },
                        "型号": {
                            "role": "model",
                            "sample_values": ["天鹰T3"],
                            "enum_values": ["天鹰T3"],
                        },
                        "车架材质": {
                            "role": None,
                            "sample_values": ["铝合金"],
                            "enum_values": ["铝合金"],
                        },
                    }
                }
            }
        }

        value_index = build_value_index(catalog)
        entity_indexes = build_entity_indexes(catalog)

        self.assertEqual(value_index["铝合金"][0]["field"], "车架材质")
        self.assertEqual(entity_indexes["brand_index"]["雅迪"][0]["field"], "品牌")
        self.assertEqual(entity_indexes["model_index"]["天鹰t3"][0]["field"], "型号")
        self.assertEqual(entity_indexes["model_values_by_length"], ["天鹰t3"])


if __name__ == "__main__":
    unittest.main()
