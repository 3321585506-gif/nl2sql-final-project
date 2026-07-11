import unittest

from src.query_ir import FieldRef, FilterCondition, FilterGroup, QueryIR


class QueryIRTest(unittest.TestCase):
    def test_round_trip(self):
        ir = QueryIR(
            select_fields=[FieldRef("electric_vehicle", "品牌")],
            filters=[
                FilterCondition(
                    field=FieldRef("electric_vehicle", "车架材质"),
                    operator="=",
                    value="铝合金",
                )
            ],
            required_tables=["electric_vehicle"],
            confidence=0.91,
            source="rule",
        )

        restored = QueryIR.from_dict(ir.to_dict())

        self.assertEqual(restored.select_fields[0].table, "electric_vehicle")
        self.assertEqual(restored.filters[0].value, "铝合金")
        self.assertIsNotNone(restored.where)
        self.assertEqual(restored.confidence, 0.91)

    def test_nested_filter_group_round_trip(self):
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

        restored = QueryIR.from_dict(ir.to_dict())

        self.assertEqual(restored.where.operator, "AND")
        self.assertIsInstance(restored.where.items[1], FilterGroup)
        self.assertEqual(restored.where.items[1].operator, "OR")


if __name__ == "__main__":
    unittest.main()
