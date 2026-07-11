# NL2SQL 结构化路由优化记录（2026-07-11）

## 背景

依据 `C:\Users\vanessa\Downloads\NL2SQL_模块优化方案与Codex任务清单.md`，本轮优化目标是把项目从“每题直接调用大模型自由生成 SQL”，逐步改造成：

```text
自然语言 -> QueryIR -> SQLCompiler -> 校验 -> 必要时 LLM 兜底
```

本轮没有追求一次性替换全部链路，而是先完成可测试、可回退的 V1 骨架。

## 已完成改动

### 1. QueryIR

新增：

```text
src/query_ir.py
tests/test_query_ir.py
```

实现：

- `FieldRef`
- `FilterCondition`
- `OrderItem`
- `QueryIR`
- `to_dict`
- `from_dict`

作用：后续规则解析器和 LLM JSON 输出都可以统一落到同一个结构化中间表示。

### 2. SQLCompiler

新增：

```text
src/sql_compiler.py
tests/test_sql_compiler.py
```

实现：

- `compile_query_ir(query_ir, join_edges, dialect="mysql")`
- 固定 SELECT / FROM / JOIN / WHERE / GROUP BY / ORDER BY / LIMIT 输出顺序
- 字符串单引号转义
- 只允许生成 SELECT
- 不自动添加 LIMIT 1

当前编译器会输出 `table.column` 形式，执行结果稳定，但字符串 EM 仍可能与标准答案不同。

### 3. SchemaCatalog

修改：

```text
src/schema_parser.py
tests/test_schema_parser_catalog.py
```

新增接口：

- `build_schema_catalog(db_path, sample_limit=20)`
- `collect_column_profile(db_path, table, column, sample_limit=20)`

支持：

- 文本列样例值
- 低基数字段枚举值
- 数值列 min/max
- 简单单位推断
- 品牌/型号列角色标记
- 常见字段别名，例如 `散热方式 -> 散热器类型`

### 4. 值索引和实体索引

修改：

```text
src/index_builder.py
tests/test_index_builder.py
```

新增接口：

- `build_value_index(schema_catalog)`
- `build_entity_indexes(schema_catalog)`

索引包括：

- `value_index`
- `brand_index`
- `model_index`
- `enum_index`
- `brand_values_by_length`
- `model_values_by_length`

作用：为后续品牌、型号、枚举值最长匹配做准备。

### 5. 三路路由骨架

修改：

```text
src/sql_generator.py
run.py
tests/test_pipeline.py
```

新增：

- `route_query(question, parser_result, cache)`
- `cache / rule / llm` 三路路由
- `route`
- `confidence`
- `stage_timings`

保持兼容：

- `predicted_sql`
- `latency`
- `error`

当前规则路径只接管保守单表等值查询；复杂范围、多条件、排序、多表查询仍交给 LLM。

### 6. evaluation 对齐修复

修改：

```text
src/evaluation.py
tests/test_evaluation.py
```

修复点：

验证集没有显式 id 时，原代码使用 `Q0000` 开始编号，而预测文件使用 `Q0001` 开始编号，导致本地评测整体错位。

当前已改为：

```text
Q0001, Q0002, ...
```

这使 Q0001 的规则 SQL 能被正确计入 EX。

## 验证结果

### 单元测试

```text
python -m unittest discover -s tests -v
```

结果：

```text
Ran 13 tests in 0.429s
OK
```

### Mock 评测

命令：

```powershell
$env:LLM_PROVIDER='mock'
$env:LLM_MODEL='mock'
python run.py --eval --limit 20
```

结果：

| 指标 | 数值 |
|---|---:|
| 样本数 | 20 |
| EM | 0.00% |
| EX | 5.00% |
| LS | 1.0000 |
| Final Score | 0.2000 |
| 平均延迟 | 0.001s |
| rule 路由 | 1 / 20 |
| llm 路由 | 19 / 20 |

说明：mock 模式下 LLM 路径固定返回 `SELECT 1;`，因此该结果只用于验证路由和本地评测链路，不代表真实 OpenAI/DeepSeek 性能。

### 真实 gpt-5.6-luna 评测

命令：

```powershell
$env:OPENAI_API_KEY=[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='gpt-5.6-luna'
Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
python run.py --eval --limit 20
```

结果：

| 指标 | 数值 |
|---|---:|
| 样本数 | 20 |
| EM | 0.00% |
| EX | 45.00% |
| LS | 0.0500 |
| Final Score | 0.0100 |
| 平均延迟 | 4.644s |
| 最大延迟 | 9.730s |
| 最小延迟 | 0.020s |
| 延迟 > 2s | 19 / 20 |
| rule 路由 | 1 / 20 |
| llm 路由 | 19 / 20 |

对比 V0 直接 LLM 基线：

| 版本 | EM | EX | LS | Final | 平均延迟 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| V0 luna 直接生成 SQL | 0.00% | 35.00% | 0.0000 | 0.0000 | 4.460s | 20/20 均走 LLM |
| V1 结构化路由 | 0.00% | 45.00% | 0.0500 | 0.0100 | 4.644s | Q0001 走规则路径，19/20 仍走 LLM |

本轮真实模型结果说明：

- 修复 evaluation id 对齐后，EX 更可信；
- 结构化规则路径至少能把 Q0001 从慢 LLM 变成约 0.02s 的快速规则 SQL；
- 因为 19/20 仍走 `gpt-5.6-luna`，平均延迟仍超过 2s，LS 只有 0.0500；
- 当前最终分从 0.0000 提升到 0.0100，但主要瓶颈仍是 LLM 路径占比太高。

### Q0001 规则路径

规则路径生成：

```sql
SELECT electric_vehicle.品牌, electric_vehicle.型号, electric_vehicle.最高时速_km_h
FROM electric_vehicle
WHERE electric_vehicle.车架材质 = '铝合金'
AND electric_vehicle.档位数量 = 3;
```

标准答案：

```sql
SELECT 品牌, 型号, 最高时速_km_h
FROM electric_vehicle
WHERE 车架材质 = '铝合金'
AND 档位数量 = 3
```

执行结果一致，EX 命中；字符串格式仍不同，EM 不命中。

## 当前限制

1. 规则解析器仍是 V1，只覆盖简单单表等值查询。
2. `SQLCompiler` 使用 `table.column`，有利于执行稳定，但本地 EM 字符串比较仍不友好。
3. 多表 JOIN、范围条件、排序、聚合尚未结构化解析。
4. `build_schema_catalog` 和新增索引接口已经实现，但尚未作为预处理产物写入 `data/processed` 并在运行时统一加载。
5. LLM 路径仍让模型输出 SQL，还没有切到“LLM 输出 QueryIR JSON”。

## 下一步建议

1. 将 `build_schema_catalog`、`build_value_index`、`build_entity_indexes` 加入预处理脚本，保存到 `data/processed`。
2. 在 `query_processor.py` 实现更完整的 `parse_query_to_ir`，优先覆盖 Q0005/Q0006/Q0011/Q0014。
3. 让 LLM 复杂路径输出 QueryIR JSON，再由 SQLCompiler 统一生成 SQL。
4. 增加 `canonicalize_sql`，把 `table.column`、无必要引号、条件顺序等格式差异从本地 EM 分析中拆出来。
5. 用真实模型重跑 20 条，比较 V0 `luna` 结果和 V1 结构化路由结果。
