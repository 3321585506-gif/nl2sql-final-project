# 基于索引优化与大模型辅助的商品问答 NL2SQL 系统项目规划文档

> 适用场景：数据结构与算法课程 Final Project  
> 比赛方向：百度智能云客悦杯：大模型挑战赛——语音客服的商品问答能力优化  
> 项目目标：构建一个面向商品数据的自然语言转 SQL（NL2SQL）系统，使用户能够用自然语言查询商品属性、价格、销量、库存、评价等信息，并返回准确 SQL、查询结果与自然语言化回答。  
> 本文档用途：  
> 1. 作为小组项目总体设计文档；  
> 2. 作为后续写 Final Project 报告的材料；  
> 3. 作为给 Codex / AI Coding 工具看的开发说明书；  
> 4. 明确 A、B 两位成员的分工、接口和协作方式。  

---

## 0. 文档使用说明

本项目需要同时满足两个要求：

1. **比赛要求**：根据自然语言 query 生成可执行 SQL，并尽量提高 SQL 准确率、降低延迟，最终按指定 JSON 格式提交预测结果。
2. **课程要求**：报告中必须体现数据结构设计、算法设计思路、核心代码模块、运行结果、测试分析、复杂度分析，以及 AI Coding 使用与代码审查过程。

因此，本项目不能只写成“调用大模型生成 SQL”，而应设计为：

> 先用数据结构和算法缩小搜索范围，再让大模型完成语义到 SQL 的转换。

本项目的核心思想是：

```text
用户自然语言问题
→ 问题预处理
→ 哈希表 / 倒排索引 / 向量索引检索相关表字段
→ 图搜索确定多表 JOIN 路径
→ 构造 Prompt
→ 大模型生成 SQL
→ SQL 安全检查与自动修复
→ 数据库执行
→ 查询结果自然语言润色
→ 输出比赛要求 JSON
```

---

## 1. 项目题目

建议项目题目：

> **基于哈希索引、倒排索引与图搜索的商品问答 NL2SQL 系统**

备用题目：

> **面向商品智能问答的自然语言转 SQL 系统设计与实现**

如果老师更希望体现数据结构课程内容，推荐使用第一个题目。

---

## 2. 团队信息与分工

> 最终报告开头需要填写真实姓名和学号。这里先用 A、B 代替。

| 成员 | 主要职责 | 具体工作 |
|---|---|---|
| A | 数据结构与算法模块负责人 | 数据集读取与预处理；数据库 schema 解析；字段别名哈希表；倒排索引；表关系图；BFS JOIN 路径搜索；复杂度分析；索引优化实验 |
| B | NL2SQL 流程与系统集成负责人 | 大模型调用接口；Prompt 构造；SQL 生成；SQL 安全检查；SQL 执行；错误修复；结果润色；JSON 提交文件生成；系统演示 |
| A + B | 共同完成 | 测试用例设计；AI Coding 日志；实验记录；Final Project 报告；代码审查；最终结果调优 |

### 2.1 A 的主要产出

A 需要重点完成以下文件：

```text
src/data_loader.py
src/schema_parser.py
src/index_builder.py
src/retriever.py
src/schema_graph.py
src/evaluation.py
tests/test_index_builder.py
tests/test_schema_graph.py
docs/complexity_analysis.md
```

A 的报告重点：

```text
数据结构设计
算法设计思路
复杂度分析
索引优化前后对比
```

### 2.2 B 的主要产出

B 需要重点完成以下文件：

```text
src/llm_client.py
src/prompt_builder.py
src/sql_generator.py
src/sql_checker.py
src/sql_executor.py
src/error_repair.py
src/answer_polisher.py
src/submission_writer.py
src/main.py
tests/test_pipeline.py
docs/ai_coding_log.md
```

B 的报告重点：

```text
NL2SQL 系统流程
Prompt 设计
SQL 生成与修复
运行结果与测试分析
AI Coding 使用与代码审查过程
```

### 2.3 协作规则

为了避免两个人 vibecoding 时互相覆盖代码，规定如下：

1. A 不直接修改 B 负责的文件。
2. B 不直接修改 A 负责的文件。
3. 共同文件必须先沟通再修改，例如 README.md、final_report.md。
4. 每次让 Codex 修改代码时，必须限制修改范围，例如“只修改 src/index_builder.py”。
5. 每次合并前必须运行测试脚本。
6. 每天记录一次实验日志和 AI Coding 日志。

---

## 3. 赛题理解

### 3.1 赛题背景

本赛题面向语音客服中的商品问答场景。真实客服中，用户常用自然语言询问商品属性、价格、库存、销量、评价、配置、续航、重量、降噪、屏幕尺寸等问题。系统需要把用户问题转换成数据库可执行的 SQL 查询，并返回准确结果。

比赛强调三个核心能力：

1. **准确回答海量商品数据查询问题**  
   面向百万级数据和上百维商品属性，系统需要正确检索商品信息。

2. **支持多表问答**  
   比赛说明中提到支持多表问答，暂定约 10 张表。因此系统不能只处理单表查询，还需要能处理多表 JOIN。

3. **低延迟生成 SQL**  
   系统要求从用户输入 query 到生成 SQL 的首字阶段低延迟，说明响应速度也是评分重点之一。

### 3.2 任务流程

比赛任务流程可以抽象为：

```text
用户 query
→ NL2SQL 系统
→ 生成 SQL 语句
→ 数据库执行
→ 查询结果
→ 结果润色
→ 返回自然语言回答
```

本项目中，我们将其细化为：

```text
输入自然语言问题
→ 识别商品类别、品牌、型号、属性、筛选条件、聚合意图、排序意图
→ 检索相关表和字段
→ 生成 SQL
→ 执行 SQL
→ 将结果转换成自然语言回答
→ 输出 predicted_sql 与 latency
```

### 3.3 简单 query 示例

```text
联想 ThinkBook 14 这款电脑的详细配置信息是什么？
华硕 OG 魔霸 7 Plus 的当前价格和性能跑分是多少？
戴尔 XPS 15 的续航时长和机身重量分别是多少？
介绍一下华为 Mate 60 Pro
小米 14 的电池容量和充电功率是多少？
AirPods Pro 2 的续航时间和价格分别是多少？
```

### 3.4 复杂 query 示例

```text
查询计算量大于 5000 且近 1 年价格变化率低于 -10% 或者近一年销量排名前 20，并且不是新品的轻薄本有哪些？

帮我找下价格在 5000 到 10000 元之间，好评率大于 95%、高性价比的笔记本电脑。

按笔记本屏幕尺寸分组统计累计销量和平均价格，按照平均价格降序排列。

查询当前售价在 4000 到 8000 元之间，支持 Wi-Fi 7，刷新率 120Hz 且库存状态为“有货”的手机，按用户评分降序排列。

按品牌分组统计：机型数量、平均当前售价、平均月销量，并按平均月销量升序排列。
```

这些复杂查询说明系统需要支持：

```text
条件筛选 WHERE
范围筛选 BETWEEN / > / <
逻辑组合 AND / OR / NOT
聚合函数 COUNT / AVG / MAX / MIN / SUM
分组 GROUP BY
排序 ORDER BY
多字段返回 SELECT 多列
多表 JOIN
```

---

## 4. 比赛提交格式设计

### 4.1 提交文件格式

比赛要求提交 JSON 文件，UTF-8 编码。基本格式如下：

```json
{
  "team_id": "TEAM001",
  "results": [
    {
      "id": "Q001",
      "query": "查询张三的套餐月费是多少",
      "predicted_sql": "SELECT monthlyfee FROM userpackage WHERE username = '张三'",
      "lantancy": "1.35s"
    },
    {
      "id": "Q002",
      "query": "哪些用户的话费余额低于50元",
      "predicted_sql": "SELECT username FROM user_info WHERE balance < 50",
      "lantancy": "1.25s"
    }
  ]
}
```

注意：截图中字段名写作 `lantancy`，不是标准拼写 `latency`。为了和比赛样例保持一致，本项目的提交模块默认输出 `lantancy` 字段。如果正式数据集或平台文档改为 `latency`，则需要在 `submission_writer.py` 中统一修改。

### 4.2 输出字段说明

| 字段 | 类型 | 是否必填 | 含义 |
|---|---|---|---|
| team_id | string | 是 | 参赛队伍 ID |
| results | array | 是 | 所有测试样本的预测结果 |
| results[].id | string | 是 | 测试样本 ID |
| results[].query | string | 是 | 原始自然语言问题 |
| results[].predicted_sql | string | 是 | 系统生成的 SQL 语句 |
| results[].lantancy | string | 是 | 从输入 query 到生成 SQL 的时间 |

---

## 5. 评分指标理解

### 5.1 SQL 准确率 EM

比赛主要指标之一是 SQL 逻辑形式准确率：

```text
EM Accuracy = 生成的 SQL 与标准 SQL 完全匹配的数量 / 总测试样本数 × 100%
```

在实际评测中，也可能执行预测 SQL 和标准 SQL，对比执行结果是否一致。因此本项目不仅追求 SQL 字符串相似，也要追求执行结果正确。

### 5.2 延迟得分 LS

初赛延迟得分用于衡量系统从用户输入 query 到生成 SQL 的响应速度。截图中的规则为：

```text
若 t ≤ 0.5s，得分 = 1.0
若 0.5s < t ≤ 1.0s，得分 = 1.0 - 0.5 × (t - 0.5)
若 1.0s < t ≤ 2.0s，得分 = 0.5 - 0.25 × (t - 1.0)
若 t > 2.0s，得分 = 0
```

平均延迟得分：

```text
LS = 所有样本延迟得分之和 / 样本总数 N
```

### 5.3 初赛总分

截图中的初赛分数为：

```text
Score = EM × 0.8 + LS × 0.2
```

因此准确率比延迟更重要，但延迟也会影响最终分数。

### 5.4 对项目设计的影响

由于 EM 占 80%，系统首先要保证 SQL 正确性。由于 LS 占 20%，不能把所有表结构、所有字段、所有样例都塞给大模型，否则 Prompt 太长，生成速度慢。

因此本项目采用：

```text
索引检索相关 schema
→ 只把最相关的表字段放入 Prompt
→ 减少 Prompt 长度
→ 降低生成延迟
→ 提高 SQL 准确率
```

---

## 6. 系统总体架构

### 6.1 总体流程

```text
用户 query
  ↓
QueryProcessor：问题预处理
  ↓
SchemaRetriever：相关表字段检索
  ↓
SchemaGraph：多表 JOIN 路径搜索
  ↓
PromptBuilder：构造 NL2SQL Prompt
  ↓
LLMClient：调用大模型
  ↓
SQLChecker：SQL 安全检查与格式化
  ↓
SQLExecutor：执行 SQL
  ↓
ErrorRepair：错误修复
  ↓
AnswerPolisher：结果润色
  ↓
SubmissionWriter：生成提交 JSON
```

### 6.2 推荐项目目录

```text
project/
├── data/
│   ├── raw/                         # 原始数据
│   ├── processed/                   # 清洗后的数据
│   └── toy/                         # 没拿到正式数据前使用的测试数据
├── database/
│   └── products.db                  # SQLite / DuckDB 数据库文件
├── src/
│   ├── config.py
│   ├── data_loader.py
│   ├── schema_parser.py
│   ├── query_processor.py
│   ├── index_builder.py
│   ├── retriever.py
│   ├── schema_graph.py
│   ├── prompt_builder.py
│   ├── llm_client.py
│   ├── sql_generator.py
│   ├── sql_checker.py
│   ├── sql_executor.py
│   ├── error_repair.py
│   ├── answer_polisher.py
│   ├── submission_writer.py
│   ├── evaluation.py
│   └── main.py
├── tests/
│   ├── test_data_loader.py
│   ├── test_index_builder.py
│   ├── test_retriever.py
│   ├── test_schema_graph.py
│   ├── test_sql_checker.py
│   └── test_pipeline.py
├── docs/
│   ├── design.md
│   ├── ai_coding_log.md
│   ├── experiment_log.md
│   ├── complexity_analysis.md
│   └── final_report_outline.md
├── outputs/
│   ├── predictions.json
│   └── logs/
├── requirements.txt
├── README.md
└── run.py
```

---

## 7. 核心数据结构设计

### 7.1 字段别名哈希表

#### 设计目的

用户问题中的表达和数据库字段名通常不同，例如：

```text
当前价格 → current_price
售价 → current_price
电池容量 → battery_capacity
续航时间 → battery_life
机身重量 → weight
好评率 → positive_rate
```

为了快速把自然语言关键词映射到数据库字段，使用哈希表。

#### 数据结构

```python
alias_map: dict[str, list[FieldRef]]
```

其中：

```python
FieldRef = {
    "table": "phone",
    "field": "battery_capacity",
    "type": "numeric",
    "description": "电池容量，单位 mAh"
}
```

#### 查找复杂度

```text
平均查找复杂度：O(1)
最坏查找复杂度：O(n)
```

#### Codex 实现要求

文件：`src/index_builder.py`

接口：

```python
def build_alias_map(schema_info: dict, extra_aliases: dict | None = None) -> dict:
    """
    根据数据库 schema 和人工补充别名，构建字段别名哈希表。

    Args:
        schema_info: schema_parser.py 解析出的数据库结构。
        extra_aliases: 人工补充的中文别名词典。

    Returns:
        alias_map: dict[str, list[dict]]
    """
```

实现步骤：

```text
1. 遍历所有表。
2. 遍历每张表的所有字段。
3. 将字段名、字段描述、中文别名加入 alias_map。
4. 一个中文词可能对应多个字段，因此 value 使用 list。
5. 对所有 key 做标准化：去空格、转小写、统一符号。
```

---

### 7.2 倒排索引

#### 设计目的

自然语言问题中可能包含多个关键词，例如：

```text
查询价格在 5000 到 10000 元之间、好评率大于 95% 的笔记本电脑
```

需要快速找到相关表和字段：

```text
价格 → current_price
好评率 → positive_rate
笔记本电脑 → laptop / computer
```

倒排索引用于实现：

```text
关键词 → 相关表字段列表
```

#### 数据结构

```python
inverted_index: dict[str, list[FieldRef]]
```

示例：

```python
{
    "价格": [
        {"table": "computer", "field": "current_price"},
        {"table": "phone", "field": "current_price"}
    ],
    "续航": [
        {"table": "computer", "field": "battery_life"},
        {"table": "earphone", "field": "battery_life"}
    ]
}
```

#### 查找复杂度

```text
不使用倒排索引：每次遍历所有字段，O(n)
使用倒排索引：关键词查找平均 O(1)，再合并候选结果 O(k)
```

#### Codex 实现要求

文件：`src/index_builder.py`

接口：

```python
def build_inverted_index(schema_info: dict, alias_map: dict) -> dict:
    """
    构建关键词到表字段的倒排索引。
    """
```

文件：`src/retriever.py`

接口：

```python
def retrieve_by_keywords(question: str, inverted_index: dict, top_k: int = 10) -> list[dict]:
    """
    根据用户问题中的关键词，从倒排索引中检索相关字段。
    """
```

实现步骤：

```text
1. 对 question 做分词或简单关键词提取。
2. 在 inverted_index 中查找每个关键词。
3. 对命中的 table-field 累加分数。
4. 按分数排序。
5. 返回 top_k 个最相关字段。
```

---

### 7.3 表关系图

#### 设计目的

比赛中包含多表问答。对于多表查询，大模型常见错误是 JOIN 路径错误，例如不知道：

```text
brand → product → sales
```

之间应该如何连接。

因此将数据库 schema 建模为图：

```text
顶点：数据表
边：外键关系或可连接字段
```

#### 数据结构

```python
schema_graph: dict[str, list[Edge]]
```

示例：

```python
{
    "product": [
        {"to": "sales", "on": "product.id = sales.product_id"},
        {"to": "review", "on": "product.id = review.product_id"}
    ],
    "sales": [
        {"to": "product", "on": "sales.product_id = product.id"}
    ]
}
```

#### 核心算法

使用 BFS 寻找最短 JOIN 路径。

例如用户问题涉及：

```text
商品品牌 + 月销量
```

如果品牌字段在 `product` 表，销量字段在 `sales` 表，则通过 BFS 找到：

```text
product → sales
```

#### 复杂度

```text
BFS 时间复杂度：O(V + E)
V：表数量
E：表连接关系数量
```

#### Codex 实现要求

文件：`src/schema_graph.py`

接口：

```python
def build_schema_graph(schema_info: dict, foreign_keys: list[dict] | None = None) -> dict:
    """
    根据 schema 和外键关系构建表关系图。
    如果数据集没有显式外键，则根据相同字段名或 xxx_id 规则推断连接关系。
    """
```

```python
def find_join_path(graph: dict, start_table: str, end_table: str) -> list[dict]:
    """
    使用 BFS 查找两张表之间的最短 JOIN 路径。
    返回边列表，例如：
    [
        {"from": "product", "to": "sales", "on": "product.id = sales.product_id"}
    ]
    """
```

```python
def find_join_subgraph(graph: dict, required_tables: list[str]) -> list[dict]:
    """
    当 query 涉及多张表时，寻找连接这些表所需的 JOIN 边。
    可以先用第一张表作为起点，分别 BFS 到其他表，再合并边。
    """
```

实现步骤：

```text
1. 将每张表作为图的一个节点。
2. 根据外键或字段命名规则添加边。
3. BFS 时使用队列 queue。
4. 使用 visited 防止重复访问。
5. 找不到路径时返回空列表，并交给 PromptBuilder 提醒大模型避免乱 JOIN。
```

---

### 7.4 查询缓存

#### 设计目的

比赛中可能出现相似问题，例如：

```text
联想 ThinkBook 14 的价格是多少？
联想 ThinkBook 14 当前售价是多少？
ThinkBook 14 卖多少钱？
```

它们生成的 SQL 可能相同。使用缓存可以减少重复生成 SQL 的时间。

#### 数据结构

```python
sql_cache: dict[str, str]
result_cache: dict[str, Any]
```

其中 key 可以是：

```text
标准化后的问题文本
SQL 文本
问题 embedding 的近似 hash
```

#### 复杂度

```text
缓存命中：O(1)
缓存未命中：走完整 NL2SQL 流程
```

#### Codex 实现要求

文件：`src/retriever.py` 或 `src/cache.py`

接口：

```python
def normalize_question(question: str) -> str:
    """
    标准化 query，用于缓存 key。
    """
```

```python
def get_cached_sql(question: str, cache: dict) -> str | None:
    """
    从缓存中读取 SQL。
    """
```

```python
def update_sql_cache(question: str, sql: str, cache: dict) -> None:
    """
    将新生成的 SQL 写入缓存。
    """
```

---

### 7.5 向量索引

#### 设计目的

哈希表和倒排索引适合处理明确关键词，但对语义相似问题不够强。例如：

```text
哪些手机比较耐用？
哪些手机续航好？
电池比较大的手机有哪些？
```

它们可能都与：

```text
battery_capacity
battery_life
power_consumption
```

有关。

可以使用向量索引检索字段描述、历史问题、示例 SQL。

#### 实现建议

考虑到本项目是课程项目，向量索引作为增强模块，不作为最小系统必需模块。

可选方案：

```text
简单方案：使用 sentence-transformers 生成 embedding，余弦相似度暴力检索。
高级方案：使用 FAISS / Chroma 建立向量索引。
```

#### Codex 实现要求

文件：`src/retriever.py`

接口：

```python
def build_vector_index(schema_docs: list[dict]) -> object:
    """
    构建字段描述或示例 SQL 的向量索引。
    最小版本可以先返回 embedding 矩阵。
    """
```

```python
def retrieve_by_vector(question: str, vector_index: object, top_k: int = 5) -> list[dict]:
    """
    使用语义相似度检索相关字段或历史样例。
    """
```

注意：

```text
如果当前环境难以安装向量库，先不要实现复杂版本。
可以先保留接口，使用关键词检索作为主流程。
```

---

## 8. 核心模块与接口设计

本章是给 Codex 看的开发说明。每个模块都应该按接口实现，不要随意改函数名。

---

### 8.1 config.py

文件：`src/config.py`

职责：

```text
集中保存路径、模型配置、数据库配置、team_id、是否启用缓存等参数。
```

接口与变量：

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DB_PATH = PROJECT_ROOT / "database" / "products.db"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "predictions.json"

TEAM_ID = "TEAM001"

LLM_PROVIDER = "openai"  # 或 "local"
LLM_MODEL = "gpt-4o-mini"

ENABLE_CACHE = True
ENABLE_VECTOR_RETRIEVAL = False
MAX_SCHEMA_FIELDS = 30
MAX_EXAMPLES = 5
```

Codex 实现要求：

```text
1. 所有路径都使用 pathlib.Path。
2. 不要在其他文件中硬编码路径。
3. team_id 后续由队伍真实 ID 替换。
```

---

### 8.2 data_loader.py

文件：`src/data_loader.py`

负责人：A

职责：

```text
读取比赛提供的 CSV / Excel / JSON 数据。
将数据统一导入 SQLite 或 DuckDB。
```

接口：

```python
def load_tables_from_directory(data_dir: str) -> dict[str, "pd.DataFrame"]:
    """
    读取目录下所有 csv/xlsx/json 文件，返回 {table_name: DataFrame}。
    """
```

```python
def save_tables_to_sqlite(tables: dict, db_path: str) -> None:
    """
    将多个 DataFrame 保存到 SQLite 数据库中。
    """
```

```python
def load_test_queries(test_file: str) -> list[dict]:
    """
    读取测试集 JSON，返回 query 列表。
    每个元素至少包含 id 和 query。
    """
```

实现步骤：

```text
1. 遍历 data_dir 下的文件。
2. 根据后缀选择 pandas.read_csv / read_excel / read_json。
3. 文件名作为表名。
4. 清理列名：去空格、转小写、替换特殊字符。
5. 保存到 SQLite。
6. 读取测试 JSON，保证返回统一格式。
```

注意事项：

```text
1. Excel 可能有多个 sheet，需要每个 sheet 转成一张表。
2. 中文列名可以保留，但建议同时建立英文/拼音别名。
3. 缺失值不要随意删除，先保留。
```

---

### 8.3 schema_parser.py

文件：`src/schema_parser.py`

负责人：A

职责：

```text
解析数据库表结构，生成给检索模块和 PromptBuilder 使用的 schema_info。
```

接口：

```python
def parse_sqlite_schema(db_path: str) -> dict:
    """
    解析 SQLite 数据库结构。

    Returns:
        {
            "tables": {
                "phone": {
                    "columns": [
                        {
                            "name": "model_name",
                            "type": "TEXT",
                            "description": "",
                            "sample_values": ["小米14", "荣耀100 Pro"]
                        }
                    ]
                }
            }
        }
    """
```

```python
def collect_sample_values(db_path: str, table: str, column: str, limit: int = 5) -> list:
    """
    从数据库中抽取字段样例值，帮助大模型理解字段含义。
    """
```

实现步骤：

```text
1. 连接 SQLite。
2. 使用 PRAGMA table_info(table_name) 获取字段名和类型。
3. 每列抽取少量非空样例值。
4. 形成 schema_info 字典。
```

---

### 8.4 query_processor.py

文件：`src/query_processor.py`

负责人：A + B

职责：

```text
对自然语言问题进行预处理，抽取品牌、型号、数值条件、排序条件、聚合意图等。
```

接口：

```python
def normalize_text(text: str) -> str:
    """
    统一中英文符号、去除多余空格、大小写归一化。
    """
```

```python
def extract_numbers_and_units(question: str) -> list[dict]:
    """
    抽取数值和单位，例如 5000mAh、95%、5000到10000元。
    """
```

```python
def detect_query_intent(question: str) -> dict:
    """
    检测查询意图。

    Returns:
        {
            "need_aggregation": True,
            "aggregation_type": "AVG",
            "need_group_by": True,
            "need_order_by": True,
            "filters": [...]
        }
    """
```

实现步骤：

```text
1. 使用正则表达式识别价格区间、百分比、容量、功率、重量等。
2. 根据关键词识别聚合意图：
   多少款 → COUNT
   平均 → AVG
   最高/最贵/最大 → MAX + ORDER BY
   最低/最便宜/最小 → MIN + ORDER BY
   按品牌/按类别/分组 → GROUP BY
3. 输出结构化意图，供 PromptBuilder 使用。
```

---

### 8.5 index_builder.py

文件：`src/index_builder.py`

负责人：A

职责：

```text
构建字段别名哈希表和倒排索引。
```

接口：

```python
def build_alias_map(schema_info: dict, extra_aliases: dict | None = None) -> dict:
    """
    构建中文词、字段名、字段描述到字段引用的哈希映射。
    """
```

```python
def build_inverted_index(schema_info: dict, alias_map: dict) -> dict:
    """
    构建关键词到表字段列表的倒排索引。
    """
```

```python
def save_index(index: dict, path: str) -> None:
    """
    保存索引到 JSON 文件。
    """
```

```python
def load_index(path: str) -> dict:
    """
    从 JSON 文件读取索引。
    """
```

实现步骤：

```text
1. 从 schema_info 中读取所有表和字段。
2. 将字段名、表名、字段描述、样例值进行分词。
3. 把每个关键词映射到相关字段。
4. 加入人工同义词词典：
   售价/价格/当前价 → current_price
   电池/电池容量 → battery_capacity
   续航/续航时间 → battery_life
   重量/机身重量 → weight
   好评/好评率 → positive_rate
5. 保存索引，避免每次运行重新构建。
```

---

### 8.6 retriever.py

文件：`src/retriever.py`

负责人：A

职责：

```text
根据用户 query 检索最相关的表、字段和示例 SQL。
```

接口：

```python
def retrieve_schema_context(
    question: str,
    schema_info: dict,
    alias_map: dict,
    inverted_index: dict,
    top_k_fields: int = 20
) -> dict:
    """
    综合哈希表和倒排索引，返回和问题最相关的 schema 上下文。

    Returns:
        {
            "tables": ["phone", "product"],
            "fields": [
                {"table": "phone", "field": "model_name", "score": 3},
                {"table": "phone", "field": "battery_capacity", "score": 2}
            ],
            "matched_keywords": ["手机", "电池容量"]
        }
    """
```

```python
def rank_fields(question: str, candidates: list[dict]) -> list[dict]:
    """
    对候选字段打分排序。
    """
```

打分规则建议：

```text
1. 问题中直接出现字段别名：+3
2. 问题中出现表名或商品类别：+2
3. 问题中出现样例值，例如具体型号：+2
4. 字段类型与问题意图匹配：+1
5. 聚合类问题中数值字段优先：+1
```

---

### 8.7 schema_graph.py

文件：`src/schema_graph.py`

负责人：A

职责：

```text
建立表关系图，并为多表查询提供 JOIN 路径。
```

接口：

```python
def build_schema_graph(schema_info: dict, foreign_keys: list[dict] | None = None) -> dict:
    """
    构建表关系图。
    """
```

```python
def infer_foreign_keys(schema_info: dict) -> list[dict]:
    """
    当数据集中没有显式外键时，根据字段名推断外键关系。
    例如 product_id、phone_id、brand_id。
    """
```

```python
def find_join_path(graph: dict, start_table: str, end_table: str) -> list[dict]:
    """
    使用 BFS 查找两张表之间的最短连接路径。
    """
```

```python
def find_join_edges_for_tables(graph: dict, tables: list[str]) -> list[dict]:
    """
    为多张表寻找需要的 JOIN 边。
    """
```

实现步骤：

```text
1. 每张表作为一个节点。
2. 根据显式外键或字段命名规则添加边。
3. BFS 查找最短路径。
4. 将路径转换成 SQL JOIN 条件。
```

---

### 8.8 prompt_builder.py

文件：`src/prompt_builder.py`

负责人：B

职责：

```text
把用户问题、相关 schema、JOIN 路径、示例 SQL 组织成 Prompt。
```

接口：

```python
def build_sql_prompt(
    question: str,
    schema_context: dict,
    join_edges: list[dict],
    intent_info: dict | None = None,
    examples: list[dict] | None = None
) -> str:
    """
    构造用于生成 SQL 的 Prompt。
    """
```

Prompt 模板建议：

```text
你是一个 NL2SQL 系统。请根据用户问题和数据库结构生成一条可执行 SQL。

要求：
1. 只输出 SQL，不要输出解释。
2. 只能使用给定的表和字段。
3. 如果需要多表查询，请优先使用给定 JOIN 条件。
4. SQL 必须是 SELECT 查询。
5. 字符串条件使用单引号。
6. 不要编造不存在的字段。

用户问题：
{question}

相关表结构：
{schema_context}

可用 JOIN 条件：
{join_edges}

识别出的查询意图：
{intent_info}

示例：
{examples}

请输出 SQL：
```

注意：

```text
Prompt 不要塞入所有表结构，只放检索出的 top-k 字段。
这是降低延迟的关键。
```

---

### 8.9 llm_client.py

文件：`src/llm_client.py`

负责人：B

职责：

```text
统一封装大模型调用，方便切换在线模型或本地模型。
```

接口：

```python
class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str | None = None):
        pass

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 256) -> str:
        """
        输入 prompt，返回模型生成文本。
        """
```

实现要求：

```text
1. temperature 默认设为 0，保证 SQL 输出稳定。
2. 只返回模型文本，不在这里解析 SQL。
3. 调用耗时在 sql_generator.py 中统计。
4. API key 不要写死在代码中，使用环境变量。
```

---

### 8.10 sql_generator.py

文件：`src/sql_generator.py`

负责人：B

职责：

```text
整合检索、Prompt、大模型，生成 SQL，并记录延迟。
```

接口：

```python
def generate_sql_for_question(
    question: str,
    schema_info: dict,
    indexes: dict,
    graph: dict,
    llm_client
) -> dict:
    """
    输入自然语言问题，输出 SQL 和延迟。

    Returns:
        {
            "question": "...",
            "predicted_sql": "SELECT ...",
            "latency": 1.23,
            "schema_context": {...},
            "join_edges": [...]
        }
    """
```

实现步骤：

```text
1. 记录开始时间 start。
2. 调用 QueryProcessor 分析问题。
3. 调用 Retriever 检索相关字段。
4. 调用 SchemaGraph 查找 JOIN 路径。
5. 调用 PromptBuilder 构造 Prompt。
6. 调用 LLMClient 生成 SQL。
7. 调用 SQLChecker 清理 SQL。
8. 记录结束时间 end。
9. latency = end - start。
10. 返回 SQL 和延迟。
```

---

### 8.11 sql_checker.py

文件：`src/sql_checker.py`

负责人：B

职责：

```text
检查 SQL 是否安全、是否只包含 SELECT、是否使用不存在的字段。
```

接口：

```python
def extract_sql(text: str) -> str:
    """
    从模型输出中提取 SQL。
    """
```

```python
def is_select_only(sql: str) -> bool:
    """
    检查是否只包含 SELECT 查询。
    禁止 DROP、DELETE、UPDATE、INSERT 等操作。
    """
```

```python
def validate_sql_schema(sql: str, schema_info: dict) -> list[str]:
    """
    检查 SQL 中的表名和字段名是否存在。
    返回错误列表。
    """
```

```python
def normalize_sql(sql: str) -> str:
    """
    格式化 SQL，去除多余换行和 markdown 代码块。
    """
```

实现要求：

```text
1. 删除 ```sql 这类 markdown 标记。
2. 只允许 SELECT。
3. 不允许多条 SQL。
4. 不允许修改数据库。
5. 如果字段不存在，返回错误给 ErrorRepair。
```

---

### 8.12 sql_executor.py

文件：`src/sql_executor.py`

负责人：B

职责：

```text
执行 SQL 查询并返回结果。
```

接口：

```python
def execute_sql(db_path: str, sql: str) -> dict:
    """
    执行 SQL。

    Returns:
        {
            "success": True,
            "rows": [...],
            "columns": [...],
            "error": None
        }
    """
```

实现要求：

```text
1. 使用 sqlite3 或 duckdb。
2. 执行前调用 is_select_only。
3. 捕获 SQL 语法错误、字段不存在、表不存在等异常。
4. 返回结构化结果，不直接 print。
```

---

### 8.13 error_repair.py

文件：`src/error_repair.py`

负责人：B

职责：

```text
当 SQL 执行失败时，根据错误信息让大模型修复 SQL。
```

接口：

```python
def repair_sql(
    question: str,
    bad_sql: str,
    error_message: str,
    schema_context: dict,
    llm_client
) -> str:
    """
    根据错误信息修复 SQL。
    """
```

实现步骤：

```text
1. 构造修复 Prompt。
2. 告诉模型原问题、错误 SQL、数据库错误信息、可用表字段。
3. 要求只输出修复后的 SQL。
4. 最多修复 1-2 次，避免延迟过高。
```

注意：

```text
比赛评分包含延迟，因此错误修复不能无限循环。
初赛中建议最多修复 1 次。
```

---

### 8.14 answer_polisher.py

文件：`src/answer_polisher.py`

负责人：B

职责：

```text
将 SQL 执行结果转成自然语言回答。
虽然初赛提交主要是 SQL，但比赛任务中包含结果润色，因此报告和演示中应保留该模块。
```

接口：

```python
def polish_answer(question: str, sql_result: dict) -> str:
    """
    将查询结果转成自然语言回答。
    """
```

实现要求：

```text
1. 如果结果只有一个值，直接回答。
2. 如果结果是多行，按列表或一句话总结。
3. 如果结果为空，回答“未查询到符合条件的商品”。
4. 不要编造数据库中没有的信息。
```

---

### 8.15 submission_writer.py

文件：`src/submission_writer.py`

负责人：B

职责：

```text
将所有测试样本的 SQL 预测结果写成比赛要求 JSON。
```

接口：

```python
def format_latency(seconds: float) -> str:
    """
    将浮点秒数转成 '1.35s' 形式。
    """
```

```python
def build_submission(team_id: str, predictions: list[dict]) -> dict:
    """
    构建提交 JSON 对象。
    """
```

```python
def save_submission(submission: dict, output_path: str) -> None:
    """
    保存 UTF-8 JSON 文件。
    """
```

实现要求：

```text
1. 确保 JSON 使用 UTF-8 编码。
2. ensure_ascii=False，避免中文转义。
3. 字段名与比赛样例保持一致。
4. 输出前检查每条结果都包含 id、query、predicted_sql、lantancy。
```

---

### 8.16 evaluation.py

文件：`src/evaluation.py`

负责人：A

职责：

```text
在本地测试集上评估 SQL 准确率、执行结果一致率和延迟得分。
```

接口：

```python
def exact_match_accuracy(pred_sqls: list[str], gold_sqls: list[str]) -> float:
    """
    计算 SQL 字符串完全匹配准确率。
    """
```

```python
def execution_match_accuracy(pred_results: list, gold_results: list) -> float:
    """
    计算执行结果一致率。
    """
```

```python
def latency_score(t: float) -> float:
    """
    根据比赛规则计算单条样本延迟得分。
    """
```

```python
def average_latency_score(latencies: list[float]) -> float:
    """
    计算平均延迟得分。
    """
```

```python
def final_score(em: float, ls: float) -> float:
    """
    初赛总分：Score = EM * 0.8 + LS * 0.2
    """
```

---

### 8.17 main.py

文件：`src/main.py`

负责人：B

职责：

```text
串联完整流程，批量处理测试集。
```

接口：

```python
def run_pipeline(test_file: str, output_path: str) -> None:
    """
    读取测试集，批量生成 SQL，保存提交文件。
    """
```

实现流程：

```text
1. 读取配置。
2. 加载数据库 schema。
3. 构建或加载索引。
4. 构建表关系图。
5. 初始化 LLMClient。
6. 读取测试 query。
7. 对每个 query 调用 generate_sql_for_question。
8. 保存 predictions.json。
```

---

## 9. 最小可运行版本计划

在正式数据集未发布前，先使用 toy dataset 开发。

### 9.1 Toy Dataset

建议创建 3 张表：

```sql
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    model_name TEXT,
    brand TEXT,
    category TEXT,
    current_price REAL,
    positive_rate REAL
);

CREATE TABLE phone (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    battery_capacity REAL,
    charging_power REAL,
    refresh_rate REAL,
    stock_status TEXT
);

CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    monthly_sales INTEGER,
    yearly_sales INTEGER
);
```

### 9.2 Toy Query

```text
联想 ThinkBook 14 的当前价格是多少？
电池容量大于 5000mAh 的手机有哪些？
按品牌统计手机的平均价格。
查询月销量大于 5000 且好评率高于 95% 的商品。
当前售价在 4000 到 8000 元之间且库存状态为有货的手机有哪些？
```

### 9.3 最小系统目标

第一版只需要实现：

```text
读取数据
解析 schema
构建倒排索引
检索相关表字段
调用大模型生成 SQL
保存 JSON
```

暂时不实现：

```text
向量索引
复杂 SQL 自动修复
网页界面
复杂结果润色
```

---

## 10. 开发阶段安排

### 阶段一：项目骨架与 toy dataset

负责人：

```text
A：建立数据读取、schema 解析、索引模块。
B：建立 LLM 调用、Prompt、SQL 生成模块。
```

目标：

```text
能用 toy dataset 生成简单 SELECT SQL。
```

完成标准：

```text
python run.py 能处理 5 条测试 query，并输出 predictions.json。
```

---

### 阶段二：加入数据结构优化

负责人：

```text
A：完成哈希表、倒排索引、图搜索、复杂度分析。
B：将 A 的检索结果接入 PromptBuilder。
```

目标：

```text
Prompt 中只包含相关表字段，而不是完整 schema。
```

完成标准：

```text
对比“完整 schema prompt”和“检索后 schema prompt”的延迟和准确率。
```

---

### 阶段三：接入正式数据集

负责人：

```text
A：分析正式数据表结构，补充字段别名和表关系。
B：调试 Prompt，批量生成 SQL，检查错误样例。
```

目标：

```text
能对比赛测试集 1 批量生成 SQL。
```

完成标准：

```text
本地生成符合格式的 JSON 文件。
```

---

### 阶段四：优化准确率与延迟

负责人：

```text
A：优化检索召回率，调整字段打分规则。
B：优化 Prompt，加入少量高质量示例，修复常见 SQL 错误。
```

目标：

```text
提高 EM，控制 latency。
```

完成标准：

```text
有实验表格记录不同版本的 EM、LS 和总分。
```

---

### 阶段五：整理报告与个人感想

负责人：

```text
A：整理数据结构设计、算法复杂度、索引优化实验。
B：整理系统流程、运行结果、AI Coding 日志。
A + B：共同完成项目设计部分，各自单独写个人心得。
```

---

## 11. 实验设计

### 11.1 对比实验一：是否使用索引检索

| 版本 | Prompt 内容 | 预期效果 |
|---|---|---|
| Baseline | 所有表结构全部输入大模型 | Prompt 长，延迟高，容易混淆字段 |
| Index-RAG | 只输入检索出的相关字段 | Prompt 短，延迟低，字段更准确 |

记录指标：

```text
平均 SQL 生成时间
SQL 准确率
错误 SQL 数量
Prompt token 长度
```

### 11.2 对比实验二：是否使用表关系图

| 版本 | JOIN 处理方式 | 预期效果 |
|---|---|---|
| 无图搜索 | 让大模型自己猜 JOIN | 多表查询容易错 |
| 图搜索 BFS | 提前给出 JOIN 条件 | 多表查询更稳定 |

记录指标：

```text
多表查询正确率
JOIN 错误数量
```

### 11.3 对比实验三：是否使用缓存

| 版本 | 重复问题处理方式 | 预期效果 |
|---|---|---|
| 无缓存 | 每次重新生成 SQL | 延迟稳定但偏高 |
| 有缓存 | 相同或相似问题复用 SQL | 重复查询接近 O(1) |

记录指标：

```text
缓存命中率
平均延迟
```

---

## 12. 复杂度分析

### 12.1 未优化 schema 查找

假设数据库共有：

```text
T 张表
C 个字段
Q 个查询
```

如果每个 query 都遍历所有字段，字段匹配复杂度为：

```text
O(C)
```

Q 个查询总复杂度：

```text
O(QC)
```

### 12.2 哈希表字段映射

字段别名到字段引用使用哈希表：

```text
单个关键词查找平均 O(1)
m 个关键词查找平均 O(m)
```

### 12.3 倒排索引检索

倒排索引结构：

```text
关键词 → 字段列表
```

若 query 中有 m 个关键词，每个关键词平均命中 k 个字段，则复杂度为：

```text
O(m + mk)
```

通常 k 远小于 C，因此比全字段扫描更快。

### 12.4 BFS JOIN 路径搜索

表关系图中：

```text
V = 表数量
E = 表连接关系数量
```

BFS 搜索复杂度：

```text
O(V + E)
```

由于比赛中表数量约 10 张，BFS 开销很小，但能显著降低多表 JOIN 错误率。

### 12.5 缓存查询

缓存命中时：

```text
O(1)
```

缓存未命中时：

```text
进入完整 NL2SQL 流程
```

### 12.6 总体复杂度

单条 query 的主要流程复杂度可近似为：

```text
O(m + mk + V + E + LLM)
```

其中 LLM 表示大模型生成 SQL 的时间。数据结构优化的意义在于减少传入大模型的 schema 长度，从而间接降低 LLM 延迟。

---

## 13. AI Coding 使用与代码审查计划

### 13.1 AI Coding 使用范围

本项目允许使用 Codex / ChatGPT 等 AI Coding 工具辅助：

```text
生成项目骨架
生成函数初稿
补充单元测试
解释报错
重构代码
生成 Prompt 模板
辅助撰写实验记录
```

但不能完全不审查 AI 代码。

### 13.2 必须人工检查的内容

```text
1. AI 是否使用了不存在的字段名。
2. AI 是否把 SQL 字符串拼接写错。
3. AI 是否没有处理空结果。
4. AI 是否没有限制危险 SQL。
5. AI 是否修改了不该修改的文件。
6. AI 是否破坏了函数接口。
7. AI 是否为了通过测试而硬编码结果。
```

### 13.3 AI Coding 日志模板

文件：`docs/ai_coding_log.md`

```markdown
# AI Coding 使用与代码审查日志

| 日期 | 使用工具 | 任务 | AI 生成内容 | 发现的问题 | 人工修改 |
|---|---|---|---|---|---|
| 2026-xx-xx | Codex | 生成倒排索引模块 | build_inverted_index 函数 | 没有处理中文别名 | 加入 alias_map |
| 2026-xx-xx | Codex | 生成 BFS JOIN 搜索 | find_join_path 函数 | 找不到路径时直接报错 | 改成返回空列表 |
| 2026-xx-xx | Codex | 生成 SQL 执行模块 | execute_sql 函数 | 没有限制 DELETE/UPDATE | 增加 is_select_only |
```

### 13.4 给 Codex 的通用规则

每次给 Codex 的 Prompt 开头都加：

```text
你只能修改我指定的文件，不要改其他文件。
不要改函数名和返回值格式。
不要删除已有测试。
代码要能直接运行。
遇到不确定字段时，不要硬编码，应该从 schema_info 读取。
所有 SQL 执行前必须检查是否为 SELECT。
```

---

## 14. 给 Codex 的分模块开发 Prompt

### 14.1 给 Codex：生成索引模块

```text
请只修改 src/index_builder.py。

目标：
实现 build_alias_map、build_inverted_index、save_index、load_index 四个函数。

要求：
1. 输入 schema_info，输出 alias_map 和 inverted_index。
2. alias_map 使用 dict[str, list[dict]]。
3. inverted_index 使用 dict[str, list[dict]]。
4. 对中文别名、字段名、表名、字段描述都建立索引。
5. 不要硬编码具体比赛字段，但可以允许传入 extra_aliases。
6. 添加必要的类型注解和异常处理。
7. 不要修改其他文件。
```

### 14.2 给 Codex：生成表关系图模块

```text
请只修改 src/schema_graph.py。

目标：
实现 infer_foreign_keys、build_schema_graph、find_join_path、find_join_edges_for_tables。

要求：
1. 使用图的邻接表表示。
2. find_join_path 必须使用 BFS。
3. 找不到路径时返回空列表，不要抛出异常。
4. 支持根据 product_id、phone_id、brand_id 这类字段名推断外键。
5. 返回 JOIN 边时包含 from、to、on 三个字段。
6. 不要修改其他文件。
```

### 14.3 给 Codex：生成 PromptBuilder

```text
请只修改 src/prompt_builder.py。

目标：
实现 build_sql_prompt 函数。

要求：
1. Prompt 必须要求模型只输出 SQL。
2. Prompt 中只能包含 schema_context 里的相关表字段，不要放完整数据库 schema。
3. 如果 join_edges 非空，要把 JOIN 条件明确提供给模型。
4. 如果 intent_info 包含聚合、排序、分组意图，要加入 Prompt。
5. Prompt 必须提醒模型只能生成 SELECT。
6. 不要修改其他文件。
```

### 14.4 给 Codex：生成 SQL 安全检查模块

```text
请只修改 src/sql_checker.py。

目标：
实现 extract_sql、is_select_only、validate_sql_schema、normalize_sql。

要求：
1. extract_sql 要能去掉 markdown 代码块。
2. is_select_only 只允许 SELECT 或 WITH 开头的查询。
3. 禁止 DROP、DELETE、UPDATE、INSERT、ALTER、CREATE。
4. validate_sql_schema 检查 SQL 中使用的表名是否在 schema_info 中。
5. 先实现基础版本，不要求完整 SQL parser。
6. 不要修改其他文件。
```

### 14.5 给 Codex：生成主流程

```text
请只修改 src/main.py 和 run.py。

目标：
实现 run_pipeline(test_file, output_path)。

要求：
1. 加载配置。
2. 解析数据库 schema。
3. 构建或加载索引。
4. 构建表关系图。
5. 初始化 LLMClient。
6. 读取测试 query。
7. 对每条 query 调用 generate_sql_for_question。
8. 保存比赛提交 JSON。
9. 运行时打印进度，但不要打印 API key。
10. 不要修改其他模块函数接口。
```

---

## 15. 风险与解决方案

### 15.1 正式数据集字段很多

风险：

```text
字段多，Prompt 太长，大模型容易混淆。
```

解决：

```text
使用倒排索引和字段打分，只保留 top-k 字段进入 Prompt。
```

### 15.2 字段中文含义不明确

风险：

```text
字段名可能是英文缩写，模型不理解。
```

解决：

```text
抽取样例值；人工补充 alias_map；在 Prompt 中加入字段说明。
```

### 15.3 多表 JOIN 容易错

风险：

```text
大模型可能编造 JOIN 条件。
```

解决：

```text
用 schema_graph 和 BFS 提前给出 JOIN 条件。
```

### 15.4 延迟超过 2 秒

风险：

```text
延迟得分变成 0。
```

解决：

```text
减少 Prompt 长度；
缓存相同 query；
temperature 设为 0；
最多修复一次 SQL；
优先使用轻量模型。
```

### 15.5 AI Coding 改坏代码

风险：

```text
Codex 修改范围过大，导致接口不一致。
```

解决：

```text
每次只让 AI 修改一个文件；
先写接口再实现；
保留测试；
合并前人工 review。
```

---

## 16. Final Project 报告可用目录

```markdown
# 基于哈希索引、倒排索引与图搜索的商品问答 NL2SQL 系统

## 1. 团队信息
### 1.1 项目题目
### 1.2 组成员
### 1.3 分工合作情况

## 2. 项目背景与问题描述
### 2.1 赛题背景
### 2.2 商品问答中的主要困难
### 2.3 本项目目标

## 3. 系统总体设计
### 3.1 系统流程
### 3.2 模块划分
### 3.3 输入输出格式

## 4. 数据结构设计
### 4.1 字段别名哈希表
### 4.2 倒排索引
### 4.3 表关系图
### 4.4 查询缓存
### 4.5 向量索引

## 5. 算法设计思路
### 5.1 问题预处理
### 5.2 相关字段检索算法
### 5.3 基于 BFS 的 JOIN 路径搜索
### 5.4 SQL 生成算法流程
### 5.5 SQL 校验与修复

## 6. 核心代码模块说明
### 6.1 数据读取模块
### 6.2 Schema 解析模块
### 6.3 索引构建模块
### 6.4 NL2SQL 生成模块
### 6.5 SQL 执行模块
### 6.6 提交文件生成模块

## 7. 运行结果与测试分析
### 7.1 测试数据说明
### 7.2 简单查询测试
### 7.3 聚合查询测试
### 7.4 多表查询测试
### 7.5 延迟测试

## 8. 复杂度分析
### 8.1 未优化查找复杂度
### 8.2 哈希表查找复杂度
### 8.3 倒排索引复杂度
### 8.4 图搜索复杂度
### 8.5 缓存复杂度

## 9. AI Coding 使用与代码审查过程
### 9.1 AI Coding 使用方式
### 9.2 AI 生成代码的问题
### 9.3 人工审查和修改
### 9.4 对 AI Coding 的反思

## 10. 个人心得感想
```

---

## 17. 个人心得写作提醒

每个人的个人心得必须不同，不能复制同一段。

A 可以重点写：

```text
我主要负责数据读取、字段索引、倒排索引和表关系图。
刚开始我以为只要把所有表结构交给大模型就可以，但测试后发现 Prompt 太长会增加延迟，也容易让模型混淆字段。
后来我把字段别名做成哈希表，把关键词到字段的关系做成倒排索引，才更理解数据结构不是只用于考试题，而是能真正减少查询范围。
在使用 Codex 时，我发现它生成的 BFS 有时没有处理找不到路径的情况，所以我手动加入了空路径判断和测试用例。
```

B 可以重点写：

```text
我主要负责 Prompt 构造、大模型调用、SQL 生成和执行模块。
一开始 AI 生成的 SQL 经常出现字段名不存在、表名不一致的问题。
后来我们先用检索模块筛选相关字段，再把字段信息放入 Prompt，SQL 的稳定性明显提高。
在使用 AI Coding 时，我发现不能直接相信 AI 生成的代码，尤其是 SQL 执行模块必须限制只允许 SELECT，避免危险操作。
通过这个项目，我对自然语言问题如何一步步转成结构化查询有了更清楚的理解。
```

最终报告中应根据真实过程改写，不能直接照抄。

---

## 18. 当前最优实施建议

当前没有正式数据集时，建议马上完成：

```text
1. 建 GitHub 仓库。
2. 建立本文件中的目录结构。
3. 用 toy dataset 跑通最小系统。
4. A 先实现 data_loader、schema_parser、index_builder、schema_graph。
5. B 先实现 llm_client、prompt_builder、sql_generator、submission_writer。
6. 每天记录 ai_coding_log.md 和 experiment_log.md。
7. 正式数据集发布后，替换数据读取和字段别名字典。
8. 根据测试集不断优化 Prompt 和索引打分。
```

本项目最终要体现的不是“我们调用了大模型”，而是：

> 我们用哈希表、倒排索引、图搜索和缓存等数据结构，把商品问答中的自然语言查询问题转化为高效、可解释、可测试的 NL2SQL 系统。
