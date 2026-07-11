import unittest

from src.query_ir import FieldRef, FilterCondition, FilterGroup, OrderItem, QueryIR
from src.sql_compiler import compile_query_ir


class SQLCompilerTest(unittest.TestCase):
    def test_compile_simple_select(self):
        ir = QueryIR(
            select_fields=[
                FieldRef("electric_vehicle", "品牌"),
                FieldRef("electric_vehicle", "型号"),
                FieldRef("electric_vehicle", "最高时速_km_h"),
            ],
            filters=[
                FilterCondition(FieldRef("electric_vehicle", "车架材质"), "=", "铝合金"),
                FilterCondition(FieldRef("electric_vehicle", "档位数量"), "=", 3),
            ],
            required_tables=["electric_vehicle"],
        )

        sql = compile_query_ir(ir)

        self.assertEqual(
            sql,
            "SELECT 品牌, 型号, 最高时速_km_h "
            "FROM electric_vehicle WHERE 车架材质 = '铝合金' "
            "AND 档位数量 = 3",
        )

    def test_compile_order_and_limit_only_when_present(self):
        ir = QueryIR(
            select_fields=[FieldRef("air_conditioner", "型号")],
            order_by=[OrderItem(FieldRef("air_conditioner", "制冷功率_W"), "ASC")],
            required_tables=["air_conditioner"],
            limit=6,
        )

        sql = compile_query_ir(ir)

        self.assertTrue(sql.endswith("ORDER BY 制冷功率_W ASC LIMIT 6"))

    def test_compile_join_requires_edge(self):
        ir = QueryIR(
            select_fields=[
                FieldRef("computer_join_main", "型号名称"),
                FieldRef("computer_join_config", "屏幕亮度nit"),
            ],
            required_tables=["computer_join_main", "computer_join_config"],
        )
        edges = [
            {
                "from": "computer_join_main",
                "to": "computer_join_config",
                "on": "computer_join_main.笔记本ID = computer_join_config.笔记本ID",
            }
        ]

        sql = compile_query_ir(ir, edges)

        self.assertIn("JOIN computer_join_config ON", sql)

    def test_compile_nested_filter_group(self):
        ir = QueryIR(
            select_fields=[FieldRef("product", "name")],
            where=FilterGroup(
                operator="AND",
                items=[
                    FilterCondition(FieldRef("product", "brand"), "=", "A"),
                    FilterGroup(
                        operator="OR",
                        items=[
                            FilterCondition(FieldRef("product", "price"), "<", 100),
                            FilterCondition(FieldRef("product", "stock"), ">", 0),
                        ],
                    ),
                ],
            ),
            required_tables=["product"],
        )

        sql = compile_query_ir(ir)

        self.assertEqual(
            sql,
            "SELECT name FROM product WHERE brand = 'A' AND (price < 100 OR stock > 0)",
        )

    def test_compile_operator_variants(self):
        ir = QueryIR(
            select_fields=[FieldRef("product", "name")],
            where=FilterGroup(
                operator="AND",
                items=[
                    FilterCondition(FieldRef("product", "price"), "BETWEEN", [10, 20]),
                    FilterCondition(FieldRef("product", "brand"), "IN", ["A", "B"]),
                    FilterCondition(FieldRef("product", "name"), "LIKE", "%Pro%"),
                    FilterCondition(FieldRef("product", "deleted_at"), "IS", None),
                    FilterCondition(FieldRef("product", "released_at"), "IS NOT", None),
                ],
            ),
            required_tables=["product"],
        )

        sql = compile_query_ir(ir)

        self.assertIn("price BETWEEN 10 AND 20", sql)
        self.assertIn("brand IN ('A', 'B')", sql)
        self.assertIn("name LIKE '%Pro%'", sql)
        self.assertIn("deleted_at IS NULL", sql)
        self.assertIn("released_at IS NOT NULL", sql)


if __name__ == "__main__":
    unittest.main()
