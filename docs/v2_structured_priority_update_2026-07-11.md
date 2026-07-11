# NL2SQL V2 结构化优先优化记录（2026-07-11）

## 本轮目标

依据 `C:\Users\vanessa\Downloads\NL2SQL_V2_针对当前结果的改进方案.md`，本轮从 V1 的“结构化骨架”继续推进，重点是：

1. 预处理产物统一落盘和加载；
2. QueryIR 支持嵌套条件；
3. SQLCompiler 输出更接近标准答案；
4. query_processor 覆盖单商品属性查询；
5. 提高规则路径覆盖率，减少 LLM 调用。

## 已完成内容

### 1. 预处理产物落盘

新增：

```text
scripts/build_artifacts.py
tests/test_build_artifacts.py
```

已生成到：

```text
data/processed/schema_catalog.json
data/processed/alias_map.json
data/processed/inverted_index.json
data/processed/value_index.json
data/processed/entity_indexes.json
data/processed/schema_graph.json
```

`run.py --eval` 启动时现在会加载并打印：

```text
Runtime artifacts loaded: alias_map, entity_indexes, inverted_index, schema_catalog, schema_graph, value_index
```

### 2. QueryIR 升级

修改：

```text
src/query_ir.py
tests/test_query_ir.py
```

新增：

```text
FilterGroup
QueryIR.where
QueryIR.distinct
```

已支持：

```text
A AND B
A OR B
A AND (B OR C)
```

并保持旧 `filters` 字段兼容。

### 3. SQLCompiler 升级

修改：

```text
src/sql_compiler.py
tests/test_sql_compiler.py
```

新增/调整：

- 单表查询默认不加 `table.column`；
- 默认不加末尾分号；
- 支持 `BETWEEN`、`IN`、`LIKE`、`IS NULL`、`IS NOT NULL`；
- 支持 `FilterGroup` 递归编译；
- Q0001 现在能生成更接近标准答案的 SQL。

### 4. query_processor 第一阶段

修改：

```text
src/query_processor.py
tests/test_query_processor.py
src/sql_generator.py
```

当前覆盖：

- 单商品属性查询；
- 型号精确索引命中；
- 型号不在样例值中时的字面量抽取，例如 `KFR-26GW/NhAa3BAk`、`911-Pro9`、`天鹰T3`；
- 字段别名映射，例如 `散热方式 -> 散热器类型`；
- 问题中字段顺序保持，用于提高 Raw EM。

## 本地验证

### 单元测试

```text
python -m unittest discover -s tests -v
```

结果：

```text
Ran 20 tests in 0.462s
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

| 指标 | V1 | V2 |
|---|---:|---:|
| EM | 5.00% | 25.00% |
| EX | 5.00% | 25.00% |
| LS | 1.0000 | 1.0000 |
| Final Score | 0.2400 | 0.4000 |
| rule 路由 | 1 / 20 | 5 / 20 |
| llm 路由 | 19 / 20 | 15 / 20 |

说明：mock 评测不代表真实模型分数，因为 LLM 路径固定返回 `SELECT 1;`。但它能说明结构化规则路径已经从 1 条扩展到 5 条，且这些规则路径可以直接命中本地标准答案。

## 当前命中的规则样本

```text
Q0001 车架材质 = 铝合金，档位数量 = 3，查询品牌/型号/最高时速
Q0006 指定空调型号，查询 WiFi/智能/语音/自清洁/睡眠模式
Q0011 指定台式机型号，查询散热器类型
Q0013 指定电动车型号，查询电池类型
Q0014 指定空调型号，查询循环风量
```

## 真实 API 评测状态

用户已授权发送 schema 和验证集问题到 OpenAI API，并提供了 `C:\Users\vanessa\Desktop\v2_luna_eval_20.txt` 的真实评测输出。

命令：

```powershell
$env:OPENAI_API_KEY=[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='gpt-5.6-luna'
Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
python run.py --eval --limit 20
```

结果：

| 指标 | V1 结构化路由 | V2 结构化优先 |
|---|---:|---:|
| 样本数 | 20 | 20 |
| EM | 0.00% | 25.00% |
| EX | 45.00% | 55.00% |
| LS | 0.0500 | 0.2500 |
| Final Score | 0.0100 | 0.2500 |
| 平均延迟 | 4.644s | 3.851s |
| 最大延迟 | 9.730s | 9.210s |
| 最小延迟 | 0.020s | 0.000s |
| rule 路由 | 1 / 20 | 5 / 20 |
| llm 路由 | 19 / 20 | 15 / 20 |

本轮真实模型结果说明：

- 规则路由从 1 条提升到 5 条，直接带来 EM、LS 和 Final Score 提升；
- EX 从 45% 提升到 55%，说明 LLM 兜底加规则路径整体执行正确率也有改善；
- 15 / 20 仍走 `gpt-5.6-luna`，平均延迟仍超过 2s，下一阶段的主要收益点仍是继续扩大规则/结构化路径覆盖率。

### DeepSeek 兼容说明

`src/llm_client.py` 继续兼容 OpenAI-compatible 接口，同时新增 `deepseek` provider 别名。同学可以任选以下一种方式接入：

```powershell
$env:DEEPSEEK_API_KEY='你的 DeepSeek key'
$env:LLM_PROVIDER='deepseek'
$env:LLM_MODEL='deepseek-chat'
python run.py --eval --limit 20
```

或：

```powershell
$env:OPENAI_API_KEY='你的 DeepSeek key'
$env:OPENAI_BASE_URL='https://api.deepseek.com/v1'
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='deepseek-chat'
python run.py --eval --limit 20
```

## 下一步

1. 继续扩展 query_processor 的范围条件、布尔枚举和 Top N 模板；
2. 增加 QueryIR Validator，防止错误规则 SQL 放行；
3. 将 LLM 路径改为输出 QueryIR JSON，而不是自由 SQL；
4. 继续把 Q0005、Q0007、Q0015、Q0016、Q0018、Q0019、Q0020 这类单表可解析问题迁入结构化规则路径。
