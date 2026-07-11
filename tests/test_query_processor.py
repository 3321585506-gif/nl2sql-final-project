import unittest

from src.query_processor import parse_query_to_ir


class QueryProcessorTest(unittest.TestCase):
    def test_parse_single_product_attribute_query(self):
        artifacts = {
            "schema_catalog": {
                "tables": {
                    "air_conditioner": {
                        "columns": {
                            "型号": {"role": "model", "aliases": ["型号"]},
                            "WiFi控制": {"role": None, "aliases": ["WiFi控制"]},
                            "智能控制": {"role": None, "aliases": ["智能控制"]},
                            "语音控制": {"role": None, "aliases": ["语音控制"]},
                        }
                    }
                }
            },
            "entity_indexes": {
                "model_index": {
                    "kfr-32gw/bp3dn8y-pc401(b1)": [
                        {
                            "table": "air_conditioner",
                            "field": "型号",
                            "value": "KFR-32GW/BP3DN8Y-PC401(B1)",
                        }
                    ]
                },
                "brand_index": {},
            },
        }

        ir = parse_query_to_ir(
            "美的酷金KFR-32GW/BP3DN8Y-PC401(B1)支持WiFi控制、智能控制和语音控制吗？",
            artifacts,
        )

        self.assertGreaterEqual(ir.confidence, 0.9)
        self.assertEqual(ir.filters[0].field.column, "型号")
        self.assertEqual(ir.filters[0].value, "KFR-32GW/BP3DN8Y-PC401(B1)")
        self.assertEqual([field.column for field in ir.select_fields], ["WiFi控制", "智能控制", "语音控制"])

    def test_parse_alias_attribute_query(self):
        artifacts = {
            "schema_catalog": {
                "tables": {
                    "desktop_computer": {
                        "columns": {
                            "型号": {"role": "model", "aliases": ["型号"]},
                            "散热器类型": {"role": None, "aliases": ["散热方式"]},
                            "散热方式": {"role": None, "aliases": ["散热方式"]},
                        }
                    }
                }
            },
            "entity_indexes": {
                "model_index": {
                    "911-pro9": [
                        {"table": "desktop_computer", "field": "型号", "value": "911-Pro9"}
                    ]
                },
                "brand_index": {},
            },
        }

        ir = parse_query_to_ir("雷神911-Pro9用的是什么散热方式？", artifacts)

        self.assertEqual([field.column for field in ir.select_fields], ["散热器类型"])
        self.assertEqual(ir.filters[0].value, "911-Pro9")

    def test_parse_model_literal_not_in_index(self):
        artifacts = {
            "schema_catalog": {
                "tables": {
                    "air_conditioner": {
                        "columns": {
                            "型号": {"role": "model", "aliases": ["型号"]},
                            "循环风量_立方米每小时": {
                                "role": None,
                                "aliases": ["循环风量"],
                            },
                        }
                    }
                }
            },
            "entity_indexes": {"model_index": {}, "brand_index": {}},
        }

        ir = parse_query_to_ir("格力KFR-26GW/NhAa3BAk这个型号的循环风量有多大？", artifacts)

        self.assertGreaterEqual(ir.confidence, 0.9)
        self.assertEqual(ir.filters[0].field.column, "型号")
        self.assertEqual(ir.filters[0].value, "KFR-26GW/NhAa3BAk")
        self.assertEqual(ir.select_fields[0].column, "循环风量_立方米每小时")


if __name__ == "__main__":
    unittest.main()
