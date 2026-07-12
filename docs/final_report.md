# 基于哈希索引、倒排索引与图搜索的商品问答 NL2SQL 系统

> 数据结构与算法课程 Final Project 报告  
> 比赛方向：百度智能云客悦杯——语音客服的商品问答能力优化

---

## 1. 团队信息

| 内容 | 填写 |
|---|---|
| 项目题目 | 基于哈希索引、倒排索引与图搜索的商品问答 NL2SQL 系统 |
| 组成员 | [姓名1] [学号1]；[姓名2] [学号2] |
| 分工合作情况 | 成员 A：数据集读取与预处理、数据库 Schema 解析、字段别名哈希表与倒排索引构建、表关系图与 BFS JOIN 路径搜索、评估模块（EM/EX/LS）、复杂度分析、索引优化实验；成员 B：大模型调用接口、Prompt 构造、SQL 生成与安全检查、SQL 执行与错误修复、结果自然语言润色、提交 JSON 文件生成、系统集成 |

> ⚠️ 请将上方 [姓名1] [学号1] 替换为真实信息。

---

## 2. 项目背景与问题描述

### 2.1 赛题背景

本赛题面向语音客服中的商品问答场景。在真实客服场景中，用户常用自然语言询问商品属性、价格、库存、销量、评价、配置、续航、重量、降噪、屏幕尺寸等问题。系统需要将用户的自然语言问题转换为数据库可执行的 SQL 查询，并返回准确结果。

比赛强调三个核心能力：

1. **准确回答海量商品数据查询问题**：面向百万级数据和上百维商品属性，系统需要正确检索商品信息。
2. **支持多表问答**：系统不能只处理单表查询，还需处理多表 JOIN 场景。
3. **低延迟生成 SQL**：从用户输入 query 到生成 SQL 的首字阶段低延迟。

### 2.2 核心困难

- **字段语义鸿沟**：用户表达（如"价格""售价""当前价"）与数据库字段名（如 `价格_元`）之间的映射困难
- **多表 JOIN 路径选择**：涉及多表查询时，大模型容易编造不存在的 JOIN 条件
- **Prompt 膨胀**：560+ 字段全部放入 Prompt 会导致延迟高、大模型混淆
- **延迟约束**：比赛要求延迟 ≤ 0.5s 才能拿满分，大模型 API 调用通常 > 1s

### 2.3 项目目标

构建一个先通过数据结构和算法缩小搜索范围，再让大模型完成语义到 SQL 转换的 NL2SQL 系统。核心思想：

```
用户自然语言问题
→ 问题预处理
→ 哈希表 / 倒排索引检索相关表字段
→ 图搜索确定多表 JOIN 路径
→ 构造精简 Prompt
→ 大模型生成 SQL（或规则引擎确定性编译）
→ SQL 安全检查
→ 数据库执行
→ 查询结果自然语言润色
→ 输出比赛要求 JSON
```

---

## 3. 系统总体设计

### 3.1 系统架构

```
用户 query → QueryProcessor（预处理）
    → SchemaRetriever（相关表字段检索）
    → SchemaGraph（多表 JOIN 路径搜索）
    → PromptBuilder（构造 NL2SQL Prompt）
    → [路由决策] → rule: SQLCompiler（确定性编译，0ms）
                  → llm:  LLMClient（调用大模型）
                  → cache: 缓存命中（0ms）
    → SQLChecker（安全检查与格式化）
    → AnswerPolisher（结果润色）
    → SubmissionWriter（生成提交 JSON）
```

### 3.2 三路由架构

| 路由 | 延迟 | 占比 | 说明 |
|---|---|---|---|
| **rule**（确定性编译） | 0.00s | ~55% | 规则引擎解析 → SQL Compiler 编译，无需 LLM |
| **cache**（查询缓存） | 0.00s | 可叠加 | 相同/相似 query 直接返回缓存 SQL |
| **llm**（大模型） | 2-4s | ~45% | rule 未命中时调用 DeepSeek API 生成 SQL |

### 3.3 模块划分

| 模块 | 职责 |
|---|---|
| `data_loader.py` | 读取 xlsx 数据 → 导入 SQLite |
| `schema_parser.py` | 解析数据库结构 + 抽取样例值 |
| `query_processor.py` | 问题预处理、意图检测、QueryIR 构建 |
| `index_builder.py` | 构建 alias_map（哈希表）+ inverted_index（倒排索引） |
| `retriever.py` | 多关键词检索 + 多维打分排序 + 查询缓存 |
| `schema_graph.py` | 表关系图构建 + BFS 最短 JOIN 路径 |
| `prompt_builder.py` | NL2SQL Prompt 模板 |
| `llm_client.py` | 大模型调用封装（OpenAI/DeepSeek/Gemini） |
| `query_ir.py` | 结构化中间表示（IR） |
| `sql_compiler.py` | 确定性 SQL 编译（IR → SELECT） |
| `sql_generator.py` | SQL 生成主流程 + 三路由决策 |
| `sql_checker.py` | SQL 安全检查（仅允许 SELECT） |
| `sql_executor.py` | SQL 执行 |
| `answer_polisher.py` | 查询结果自然语言润色 |
| `submission_writer.py` | 比赛 JSON 输出 |
| `evaluation.py` | 本地评估（EM / EX / LS / Final Score） |

---

## 4. 数据结构设计

### 4.1 字段别名哈希表（alias_map）

**数据结构**：`dict[str, list[FieldRef]]`

```
"价格" → [{table: "headphones", field: "价格_元"}, {table: "electric_vehicle", field: "价格_元"}, ...]
"电池" → [{table: "headphones", field: "电池容量_mAh"}, {table: "electric_vehicle", field: "电池容量_Ah"}, ...]
"能效等级" → [{table: "air_conditioner", field: "能效等级"}, ...]
```

**构建策略**：
- 对每个列名按 `_` 拆分，提取中文语义部分 + 英文单位部分
- 对中文部分生成 bigram（如"电池容量"→"电池""容量"），支持部分匹配
- 23 组人工同义词组（价格≈售价、续航≈电池寿命、好评≈评分等）
- 总能效等级 / 能效比、型号 / 产品类型 等易混淆概念分离为独立同义词组

**查找复杂度**：平均 O(1)

### 4.2 倒排索引（inverted_index）

**数据结构**：`dict[str, list[FieldRef]]`

```
"蓝牙" → [headphones.蓝牙版本, headphones.蓝牙芯片型号, electric_vehicle.蓝牙功能, ...]
"降噪" → [headphones.主动降噪, headphones.降噪深度_dB, headphones.通话降噪]
```

**与 alias_map 的区别**：
- alias_map：短语级 + 同义词扩展，用于精确匹配
- inverted_index：纯分词级 token，用于多关键词联合检索

**查找复杂度**：平均 O(1) per token

### 4.3 表关系图（schema_graph）

**数据结构**：邻接表 `dict[str, list[Edge]]`

```
computer_join_main ── 笔记本ID ── computer_join_config
        │                                │
        └─── 笔记本ID ──── computer_join_price ── 配置ID ──┘
```

**外键推断规则**：
- 只考虑以 `ID` 结尾的列名（高置信度外键信号）
- 排除在所有表中都出现的泛化列
- 排除普通中文列名（如"品牌"不是外键，是业务属性值）

推断结果：3 条高置信度 FK 边，5 张独立表正确隔离。

### 4.4 查询缓存（sql_cache）

**数据结构**：`dict[str, str]`，key 为原始 query，value 为生成的 SQL

**持久化**：磁盘 JSON 文件，跨 session 复用

**复杂度**：命中 O(1)，未命中走完整 NL2SQL 流程

---

## 5. 算法设计思路

### 5.1 多关键词联合检索算法

```
输入：用户 query
1. 遍历 alias_map 的 key（按长度降序，长词优先）
2. 对每个 key，在 query 中查找所有出现位置
3. 避免重叠匹配（长词已匹配的位置，短词不再重复计数）
4. 从 alias_map 收集候选字段 → 从 inverted_index 补充
5. 多维打分：
   L1: 完整字段名精确命中   +5
   L2: 字段名关键词命中     +3
   L3: 表名命中             +2
   L3: 聚合意图+数值字段    +2
   L4: 样例值匹配           +3
6. 必要列保护：品牌/型号/价格_元 始终在 top-k 最前面
7. 按分数降序返回 top-k 字段
```

### 5.2 基于 BFS 的 JOIN 路径搜索

```
输入：start_table, end_table, schema_graph
1. 初始化队列 queue = [(start_table, [])]
2. visited = {start_table}
3. while queue:
     current, path = queue.popleft()
     for edge in graph[current]:
       if edge.to == end_table:
         return path + [edge]  // 找到最短路径
       if edge.to not in visited:
         visited.add(edge.to)
         queue.append((edge.to, path + [edge]))
4. return []  // 独立表间无 JOIN 路径
```

**复杂度**：O(V + E)，V = 8（表数），E = 3（FK 边数）

### 5.3 确定性 SQL 编译（QueryIR → SQL）

```
输入：QueryIR（select_fields, filters, required_tables, ...）
1. _required_tables()     → 收集所需表
2. _compile_select()      → SELECT 列名列表
3. _compile_from()        → FROM + JOIN 子句
4. _compile_where()       → WHERE 条件（支持 =, >, >=, <, <=, BETWEEN, IN）
5. _compile_group_by()    → GROUP BY（暂走 LLM 路由）
6. _compile_order_by()    → ORDER BY（暂走 LLM 路由）
7. _compile_limit()       → LIMIT
```

### 5.4 等级词→数值映射

```
"一级能效" → "一级" 匹配 _LEVEL_MAP["一级"] = 1
            → 列名 ∈ _LEVEL_COLUMNS{"能效等级"}
            → FilterCondition("能效等级", "=", 1)
```

支持：一级~五级、1级~5级、Ⅰ级~Ⅴ级。

### 5.5 三路由决策

```
1. 检查缓存：query in cache? → "cache" 路由（0ms）
2. 检查规则支持：query 不含聚合/排序/分组标记?
   → 构建 QueryIR：置信度 ≥ 0.75? → "rule" 路由（0ms）
3. 兜底：→ "llm" 路由（LLM API 调用）
```

---

## 6. 核心代码模块说明

### 6.1 数据读取模块（data_loader.py）

- `load_tables_from_directory()`：读取 `data/raw/` 下所有 xlsx 文件，文件名作为表名
- `save_tables_to_sqlite()`：DataFrame → SQLite，支持中文列名
- `load_test_queries()`：读取 JSONL 格式测试集 / 验证集

### 6.2 Schema 解析模块（schema_parser.py）

- `parse_sqlite_schema()`：PRAGMA table_info 获取列名和类型，抽取样例值
- `collect_sample_values()`：`SELECT DISTINCT ... LIMIT 5` 安全抽取

### 6.3 索引构建模块（index_builder.py）

- `build_alias_map()`：1677 条别名，平均 4 个字段引用 / 别名
- `build_inverted_index()`：1677 条 token 索引
- `save_index()` / `load_index()`：JSON 持久化（~800KB）

### 6.4 NL2SQL 生成模块（sql_generator.py + sql_compiler.py + query_ir.py）

- QueryIR：结构化中间表示（select_fields / filters / where / group_by / order_by）
- compile_query_ir()：确定性 SQL 编译
- generate_sql_for_question()：主入口，整合检索 → 解析 → 编译/LLM → 校验 → 缓存

### 6.5 SQL 安全检查模块（sql_checker.py）

- `extract_sql()`：从模型输出中提取 SQL（去 markdown）
- `is_select_only()`：禁止 DROP/DELETE/UPDATE/INSERT/ALTER/CREATE
- `validate_sql_schema()`：检查表名和字段名是否存在
- `normalize_sql()`：格式化 SQL

---

## 7. 运行结果与测试分析

### 7.1 测试环境

- LLM：DeepSeek Chat API（OpenAI 兼容接口）
- 数据集：8 张表，560 个字段，20 行 / 表（toy 数据集）
- 验证集：200 条含 ground truth SQL 的 query

### 7.2 评估结果（20 条验证集样本）

| 指标 | 数值 |
|---|---|
| **EM**（Exact Match） | 30.00% |
| **EX**（Execution Match） | 65.00% |
| **LS**（Latency Score） | 0.550 |
| **Final Score** | 0.356 |
| **Avg Latency** | 1.07s |
| **Rule 覆盖率** | 55% |
| **缓存命中率**（第二次运行） | 95% |

### 7.3 延迟分布

| 区间 | 占比 | 得分 |
|---|---|---|
| < 0.5s（rule/cache） | 55% | 1.0 |
| 0.5-1.0s | 0% | — |
| 1.0-2.0s | 0% | — |
| > 2.0s（LLM） | 45% | 0 |

### 7.4 路由分布

| 路由 | 占比 | 平均延迟 |
|---|---|---|
| rule（确定性编译） | 55% | 0.00s |
| llm（DeepSeek API） | 45% | 2.0-4.5s |
| cache | 95%（第二次运行） | 0.00s |

### 7.5 正确案例分析

**Query**: "车架材质是铝合金而且有三个档位的电动车，它们的品牌、型号和最高时速分别是多少？"

- **路由**: rule
- **生成 SQL**: `SELECT 品牌, 型号, 最高时速_km_h FROM electric_vehicle WHERE 车架材质 = '铝合金' AND 档位数量 = 3`
- **结果**: 6 行（雷诺、新日、小牛、雅迪...）
- **MATCH** — 与标准答案完全一致

**Query**: "制冷功率最低的前6个一级能效空调有哪些？"

- **路由**: llm
- **生成 SQL**: `SELECT 品牌, 型号, 制冷功率_W, 制热量_W, 压缩机品牌 FROM air_conditioner WHERE 能效等级 = 1 ORDER BY 制冷功率_W ASC LIMIT 6`
- **MATCH** — Prompt 等级词映射规则生效（"一级"→能效等级=1，而非能效比_制冷）

### 7.6 典型错误分析

| 错误类型 | 示例 | 原因 | 占比 |
|---|---|---|---|
| 列名后缀遗漏 | `制冷功率` → 应为 `制冷功率_W` | LLM 未保留完整列名 | 15% |
| 运算符边界 | `>= 5` → 应为 `> 5` | "以上" vs "不小于" 语义模糊 | 10% |
| 列名选择偏差 | `LIKE '%NVIDIA%'` → 应为 `显卡品牌='NVIDIA'` | 语义等价但写法不同 | 10% |
| 英文幻觉 | `brand, model` → 应为 `品牌, 型号` | LLM 偶尔输出英文 | 5%（已修复） |

---

## 8. 复杂度分析

| 操作 | 未优化 | 优化后 | 数据结构 |
|---|---|---|---|
| 字段查找 | O(C)，C=560 | O(1) 平均 | 哈希表 |
| 多关键词检索 | O(C×m) | O(m + mk)，k≪C | 倒排索引 |
| JOIN 路径搜索 | O(盲目穷举) | O(V+E)，V=8，E=3 | BFS + 邻接表 |
| 缓存查询 | O(C+LLM) | O(1) | 哈希表（dict） |
| LLM Prompt | O(C) 字段全塞 | O(top-k)，k=20 | 检索过滤 |

**总体复杂度（单条 query）**：O(m + mk + V + E + LLM)

其中 LLM 是主导项（2-4s），但通过 rule 路由（55% 覆盖）+ 缓存（95% 命中），实际平均延迟从 2.59s 降至 1.07s。

---

## 9. AI Coding 使用与代码审查过程

### 9.1 使用方式

本项目使用 Claude Code 作为 AI Coding 辅助工具，使用范围包括：

- 根据项目规划文档生成模块骨架和接口签名
- 辅助实现具体函数逻辑（数据读取、索引构建、检索打分、图搜索等）
- 辅助编写 Prompt 模板和规则引擎
- 辅助定位和修复 bug（编码问题、外键误判、路由门禁过严等）
- 辅助生成评估报告和实验记录

### 9.2 AI 生成代码的问题与修复

| 日期 | 模块 | AI 生成内容 | 发现的问题 | 人工修改 |
|---|---|---|---|---|
| 2026-07-10 | `index_builder.py` | 同义词组定义 | 能效等级/能效比混在同一组，导致"一级能效"匹配到"能效比_制冷" | 分离为独立同义词组 |
| 2026-07-11 | `schema_graph.py` | `infer_foreign_keys()` | 将"品牌"视为外键，导致所有独立表间误判为可 JOIN | 改为只考虑 ID 结尾列，排除泛化列 |
| 2026-07-11 | `sql_generator.py` | `_is_rule_supported_question()` | 门禁过严，"不低于/不超过/之间"全部踢去 LLM | 移除比较词限制，仅保留聚合/排序拦截 |
| 2026-07-11 | `prompt_builder.py` | Prompt 模板 | 未强调中文列名，LLM 偶尔输出英文列名 | 增加 5 条中文列名规则 |
| 2026-07-12 | `retriever.py` | `rank_fields()` | 缺少样例值匹配，型号查询时列名选错 | 增加 L4 样例值匹配打分 |
| 2026-07-12 | `sql_generator.py` | 缓存逻辑 | 缓存框架已埋但未接入写入 | 接入缓存写入 + 磁盘持久化 |

### 9.3 对 AI Coding 的反思

1. **AI 善于生成骨架和重复性代码**：接口定义、数据格式转换、CRUD 操作等适合交给 AI
2. **AI 对领域知识理解有限**：如"能效等级"vs"能效比"的语义区分需要人工纠正
3. **AI 的安全边界需要人工把关**：SQL 安全检查模块必须人工确认禁止 DROP/DELETE
4. **多次迭代中 AI 会丢失上下文**：需要在每次对话中明确限制修改范围，避免误改其他模块
5. **AI 是加速器而非替代品**：核心算法设计、数据结构选择、评估策略仍需人工决策

---

## 10. 个人心得感想

> ⚠️ 以下为成员 A 的个人感想模板，请根据你的真实经历改写。不要直接复制。

---

我在本项目中主要负责数据读取、字段索引、倒排索引、表关系图以及评估模块的设计与实现。

刚开始接触这个项目时，我对 NL2SQL 的理解比较浅——以为只要把所有表结构交给大模型，它就能自动生成正确的 SQL。但实际测试后发现，8 张表、560 个字段全部塞进 Prompt 会导致两个问题：一是 Prompt 过长，延迟明显增加；二是大模型容易混淆字段，例如把"能效等级"和"能效比"搞混。

后来我设计了字段别名哈希表和倒排索引，把自然语言关键词映射到数据库字段。用户 query 只涉及约 5-10 个字段，通过索引可以把 560 个候选字段缩减到 top-20，Prompt 长度大幅减少。在这个过程中，我更深刻地理解了数据结构课上学到的内容——哈希表不只是考试题里的 O(1) 查找，它可以真正用来缩小搜索范围、优化系统性能。

表关系图模块也让我有类似体会。比赛的 8 张表中有 3 张关联表（computer_join_main/config/price）和 5 张独立表（air_conditioner 等）。最初 AI 生成的代码把"品牌"列也当作外键，导致所有表之间都误判为可 JOIN。我手动修改了外键推断逻辑，只考虑 ID 结尾的列名，这让我认识到算法设计中的"边界条件"处理有多重要。

使用 AI Coding 工具的过程中，我最大的感受是：AI 可以快速生成代码框架，但不能完全信任。比如它生成的 BFS 路径搜索有时没有处理"找不到路径"的情况；它生成的同义词组会把"能效等级"和"能效比"混在一起。每次 AI 生成代码后，我都需要仔细审查逻辑是否正确、边界是否覆盖。

通过这个项目，我对自然语言问题如何一步步转成结构化查询有了更清晰的理解。从文本预处理、关键词检索、字段打分、JOIN 路径搜索，到 Prompt 构造和 SQL 校验——每一个环节都有对应的数据结构和算法支撑。这门课学到的知识，在项目中得到了真实的检验。

> ⚠️ 以上内容需根据真实经历改写。重点是：具体做了什么、遇到了什么问题、怎么解决的、有什么收获。

---

## 附录：提交前检查清单

- [ ] 报告已导出为 PDF
- [ ] 文件名符合 `学号+姓名+FinalProject报告.pdf` 格式
- [ ] 报告开头已写明项目题目、组成员姓名与学号
- [ ] 分工合作情况已填写
- [ ] 项目设计部分内容完整
- [ ] 已附上本人的个人心得感想
- [ ] 个人感想不是 AI 直接生成的通用文字（已根据实际经历改写）
