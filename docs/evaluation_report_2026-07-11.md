# NL2SQL 验证集评测记录（2026-07-11）

## 1. 同步状态

- 远端仓库：`3321585506-gif/nl2sql-final-project`
- 同步分支：`master`
- 同步到本地的远端提交：`3ece73dd8bbd8e10be27c8454119040b3c4e6ca3`
- 最新提交说明：`优化: retriever打分v2 + 必要列保护 + MAX_SCHEMA_FIELDS=20`

本地已同步同学完成的 A 模块，包括：

- `src/data_loader.py`
- `src/schema_parser.py`
- `src/index_builder.py`
- `src/retriever.py`
- `src/schema_graph.py`
- `src/evaluation.py`
- `data/processed/alias_map.json`
- `data/processed/inverted_index.json`
- `run_eval.py`
- `run_query.py`

## 2. 运行环境检查

### 2.1 Python 依赖

本机 Codex bundled Python 检查结果：

| 依赖 | 是否可用 |
|---|---:|
| `pandas` | 是 |
| `openpyxl` | 是 |
| `openai` | 否 |

我已修正 `src/llm_client.py`：当没有安装 `openai` 包时，会使用标准库 `urllib` 调用 OpenAI-compatible `/chat/completions` 接口；同时支持 `OPENAI_BASE_URL`，可用于 DeepSeek。

### 2.2 LLM 环境变量

当前本机环境变量检查结果：

| 环境变量 | 是否存在 |
|---|---:|
| `OPENAI_API_KEY` | 否 |
| `OPENAI_BASE_URL` | 否 |
| `LLM_PROVIDER` | 未设置 |
| `LLM_MODEL` | 未设置 |

因此，本次无法真实调用 DeepSeek API。直接调用 `LLMClient("openai", "deepseek-chat")` 会报：

```text
RuntimeError: OPENAI_API_KEY is required for provider='openai'
```

`run_eval.py` 没有崩溃，是因为 `src/sql_generator.py` 捕获了 LLM 异常并降级为兜底 SQL，例如：

```sql
SELECT * FROM electric_vehicle LIMIT 20;
```

所以本报告中的“本机真实配置评测”不是 DeepSeek 真实效果，而是“缺少 API key 时的兜底结果”。

## 3. 数据库构建结果

已运行：

```bash
python -m src.data_loader
```

生成数据库：

```text
database/products.db
```

构建结果：

| 表名 | 行数 | 列数 |
|---|---:|---:|
| `air_conditioner` | 20 | 70 |
| `computer_join_config` | 20 | 70 |
| `computer_join_main` | 20 | 70 |
| `computer_join_price` | 20 | 70 |
| `desktop_computer` | 20 | 70 |
| `digital_camera` | 20 | 70 |
| `electric_vehicle` | 20 | 70 |
| `headphones` | 20 | 70 |

合计：8 张表，160 行，560 个字段。

## 4. 单元测试结果

已运行：

```bash
python -m unittest discover -s tests -v
```

结果：

```text
Ran 5 tests in 0.447s
OK
```

覆盖点：

- SQL 安全检查可以拦截 `DELETE` 和多语句危险 SQL。
- schema 校验可识别已知表和字段。
- SQLite SELECT 执行返回结构化结果。
- 提交 JSON 使用比赛样例字段名 `lantancy`。
- `run_pipeline_with_context` 可在显式传入 schema 时跑通 B 侧流程。

## 5. 评估脚本运行结果

### 5.1 Mock 模式评估

运行命令：

```bash
LLM_PROVIDER=mock python run_eval.py --limit 20
```

说明：mock 模式固定返回 `SELECT 1;`，只用于验证评估链路是否跑通，不代表真实比赛性能。

结果：

| 指标 | 数值 |
|---|---:|
| 样本数 | 20 |
| EM | 0.00% |
| EX | 0.00% |
| LS | 1.0000 |
| Final Score | 0.2000 |
| 平均延迟 | 0.001s |
| 最大延迟 | 0.020s |
| 最小延迟 | 0.000s |

结论：评估链路可用，但 SQL 恒为 `SELECT 1;`，准确率为 0。

### 5.2 本机真实配置评估（无 API key，触发兜底）

运行命令：

```bash
python run_eval.py --limit 20
```

由于未设置 `OPENAI_API_KEY`，LLM 实际没有调用成功，系统使用兜底 SQL。

结果：

| 指标 | 数值 |
|---|---:|
| 样本数 | 20 |
| EM | 0.00% |
| EX | 0.00% |
| LS | 1.0000 |
| Final Score | 0.2000 |
| 平均延迟 | 0.000s |
| 最大延迟 | 0.000s |
| 最小延迟 | 0.000s |

典型预测：

| 样本 | 问题摘要 | 预测 SQL | 标准 SQL 摘要 |
|---:|---|---|---|
| 1 | 铝合金、三个档位电动车 | `SELECT * FROM electric_vehicle LIMIT 20;` | 查询品牌、型号、最高时速并带过滤条件 |
| 2 | LG 笔记本、刷新率、亮度 | `SELECT * FROM computer_join_main LIMIT 20;` | 多表 JOIN 查询型号、SKU、刷新率、亮度、价格 |
| 6 | 美的空调 WiFi/智能控制 | `SELECT * FROM air_conditioner LIMIT 20;` | 查询 WiFi、智能控制、语音控制等指定字段 |

结论：本机当前缺少 API key 时，结果不能代表同学截图里的 DeepSeek 真实评测。

## 6. 与同学截图结果对照

截图给出的三轮结果：

| 版本 | 改动 | EM | EX | 平均延迟 |
|---|---|---:|---:|---:|
| v1 原始 | `MAX=30`，基础打分 | 20% | 未给出 | 2.66s |
| v2 Few-shot | `MAX=15`，Few-shot | 0% | 20% | 2.53s |
| v3 当前 | `MAX=20`，分级打分，必要列保护 | 0% | 30% | 2.59s |

按 `src/evaluation.py` 中写明的比赛延迟得分函数：

```text
t <= 0.5s       -> 1.0
0.5s < t <= 1.0 -> 1.0 - 0.5 * (t - 0.5)
1.0s < t <= 2.0 -> 0.5 - 0.25 * (t - 1.0)
t > 2.0s        -> 0.0
```

截图中的平均延迟均大于 2 秒，因此如果按该函数粗略估计平均延迟得分，LS 接近 0。初赛总分公式是：

```text
Final Score = EM * 0.8 + LS * 0.2
```

因此：

| 版本 | EM | 平均延迟 | 估计 LS | 估计 Final Score |
|---|---:|---:|---:|---:|
| v1 原始 | 20% | 2.66s | 0.0 | 0.1600 |
| v2 Few-shot | 0% | 2.53s | 0.0 | 0.0000 |
| v3 当前 | 0% | 2.59s | 0.0 | 0.0000 |

注意：EX 是很有价值的调试指标，说明执行结果已有改善；但按当前 `evaluation.py` 的比赛总分公式，Final Score 只使用 EM 和 LS，不使用 EX。

## 7. 当前审查结论

### 7.1 已经跑通的部分

- A 模块已能解析 SQLite schema：8 张表、560 列。
- 预构建索引可加载：`alias_map.json` 和 `inverted_index.json` 均为 1677 entries。
- 表关系图可构建：推断 3 条外键关系，连接 3 张笔记本相关表。
- 数据库可从 Excel 重建。
- 单元测试通过。
- 评估脚本可完整输出 EM、EX、LS、Final Score 和延迟分布。

### 7.2 当前主要问题

| 问题 | 影响 | 证据 |
|---|---|---|
| 本机未配置 DeepSeek/OpenAI API | 无法复现截图中的真实 LLM 评测 | `OPENAI_API_KEY=False`，直接调用时报 `OPENAI_API_KEY is required` |
| 当前延迟大于 2s | 按比赛公式 LS 为 0 | 截图 v3 平均延迟 2.59s |
| EM 仍为 0% | 按比赛公式 Final Score 会很低 | 截图 v2/v3 均为 0% EM |
| EX 提升但未进入总分公式 | 可作为优化方向，但不能直接提高比赛分 | `final_score(em, ls)` 只使用 EM 和 LS |

### 7.3 代码层面已修复

- `src/llm_client.py` 已支持 `OPENAI_BASE_URL`，可用于 DeepSeek。
- `src/llm_client.py` 在没有安装 `openai` 包时，会用标准库 HTTP 请求调用兼容接口。
- `tests/test_pipeline.py` 已改为读取 `config.TEAM_ID`，避免队伍 ID 更新后测试失败。

## 8. 建议下一步

1. 在本机设置真实 DeepSeek 环境变量后重跑：

```powershell
$env:OPENAI_API_KEY="你的 DeepSeek API Key"
$env:OPENAI_BASE_URL="https://api.deepseek.com/v1"
python run_eval.py --limit 20
```

2. 如果 20 条结果稳定，再跑完整验证集：

```powershell
python run_eval.py --full
```

3. 优先优化两个方向：

- 延迟：当前截图平均 2.59s，已经超过 LS 得分阈值；需要把平均延迟压到 2s 内，最好 1s 内。
- EM：当前 v3 虽然 EX=30%，但 EM=0%；如果比赛严格按 EM，需要让 SQL 字符串结构、字段顺序、条件写法更贴近标准答案。

4. 评估输出建议同时保留 EM 和 EX：

- EM 用于比赛公式。
- EX 用于判断语义正确但字符串不一致的样例，指导 Prompt 优化。
