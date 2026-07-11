"""
根据用户 query 检索最相关的表、字段和示例 SQL。

负责人：A

检索流程：
1. 问题预处理（归一化、去噪）
2. 在 alias_map 中做关键词匹配 → 收集候选字段
3. 在 inverted_index 中做分词匹配 → 补充候选字段
4. 多维度打分排序 → 返回 top-k 字段
5. 附带返回：相关表名、匹配到的关键词、字段分组（按表）

打分规则（rank_fields）：
  +3 : query 中直接出现字段别名
  +2 : query 中出现表名或品类关键词
  +2 : query 中出现字段样例值（如具体品牌名/型号）
  +1 : 字段类型与 query 意图匹配（聚合 → 数值字段优先）
"""

import re
from pathlib import Path


# ========== 文本预处理 ==========

def normalize_question(question: str) -> str:
    """
    标准化 query，用于缓存 key 和检索匹配。

    操作：
    - 统一中英文标点
    - 去除多余空格和换行
    - 保留中文、英文、数字和下划线

    Args:
        question: 原始 query

    Returns:
        标准化后的文本
    """
    # 归一化空白
    text = re.sub(r'\s+', ' ', question.strip())
    # 全角括号 → 半角
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('，', ',').replace('。', '.')
    text = text.replace('：', ':').replace('；', ';')
    # 去除不可见字符
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


# ========== 关键词提取 ==========

def _extract_keywords_from_question(question: str, alias_map: dict) -> dict[str, int]:
    """
    从 query 中提取能与 alias_map 匹配的关键词。

    策略：
    - 遍历 alias_map 的 key，检查是否出现在 question 中
    - key 越长，权重越高（长词匹配更精准）
    - 返回 {keyword: match_count}

    Args:
        question: 标准化后的 query
        alias_map: 别名哈希表

    Returns:
        {keyword: match_score}
    """
    matched: dict[str, int] = {}
    q_lower = question.lower()

    # 按 key 长度降序，优先匹配长词（如"电池容量"优先于"电池"）
    sorted_keys = sorted(alias_map.keys(), key=len, reverse=True)

    # 记录已匹配的位置，避免同一位置重复匹配短词
    matched_positions: set[int] = set()

    for key in sorted_keys:
        if len(key) < 2:  # 跳过单字（噪音太大）
            continue

        # 在 question 中查找所有出现位置
        start = 0
        count = 0
        key_lower = key.lower()
        while True:
            pos = q_lower.find(key_lower, start)
            if pos == -1:
                break
            # 检查是否与已匹配的长词位置重叠
            key_range = set(range(pos, pos + len(key)))
            overlap = len(key_range & matched_positions)
            if overlap < len(key_range) // 2:  # 重叠不超过一半
                count += 1
                matched_positions.update(key_range)
            start = pos + 1

        if count > 0:
            # 基础分 = 词长加权，长词匹配更值钱
            matched[key] = count * min(len(key), 6)

    return matched


def _extract_numbers_from_question(question: str) -> list[dict]:
    """
    从 query 中提取数值条件和单位。

    Returns:
        [{"value": "5000", "unit": "元", "range": "5000-10000"}, ...]
    """
    results: list[dict] = []

    # 匹配数值 + 可选单位
    patterns = [
        (r'(\d+\.?\d*)\s*[-到至]\s*(\d+\.?\d*)\s*([a-zA-Z]*[元块瓦度分贝毫安升寸斤克秒时年月日天]*)', 'range'),
        (r'[大于超过高于不少于]+\s*(\d+\.?\d*)\s*([a-zA-Z]*[元块瓦度分贝毫安升寸斤克秒时]*)', 'gt'),
        (r'[小于低于不超过少于]+\s*(\d+\.?\d*)\s*([a-zA-Z]*[元块瓦度分贝毫安升寸斤克秒时]*)', 'lt'),
        (r'(\d+\.?\d*)\s*([a-zA-Z]*[元块瓦度分贝毫安升寸斤克秒时]以上)', 'gte'),
        (r'(\d+\.?\d*)\s*([a-zA-Z]*[以上以下以内])', 'gte'),
    ]

    for pattern, condition_type in patterns:
        for match in re.finditer(pattern, question):
            results.append({
                "type": condition_type,
                "text": match.group(0),
            })

    return results


# ========== 核心检索 ==========

def retrieve_by_keywords(
    question: str,
    inverted_index: dict,
    top_k: int = 10
) -> list[dict]:
    """
    根据用户问题中的关键词，从倒排索引中检索相关字段。

    纯关键词级别的检索，不做打分排序。

    Args:
        question: 标准化后的 query
        inverted_index: 倒排索引
        top_k: 返回字段数量上限

    Returns:
        字段引用列表 [{table, field, type}, ...]
    """
    matched_keywords = _extract_keywords_from_question(question, inverted_index)
    seen: set[tuple[str, str]] = set()
    results: list[dict] = []

    # 按匹配分排序关键词
    sorted_kw = sorted(matched_keywords.items(), key=lambda x: x[1], reverse=True)

    for kw, _ in sorted_kw:
        if kw in inverted_index:
            for ref in inverted_index[kw]:
                key = (ref["table"], ref["field"])
                if key not in seen:
                    seen.add(key)
                    results.append(dict(ref))
                    if len(results) >= top_k:
                        return results

    return results


def rank_fields(
    question: str,
    candidates: list[dict],
    schema_info: dict | None = None
) -> list[dict]:
    """
    对候选字段打分排序（v2 优化版）。

    打分规则（分层）：
    L1 精确匹配:
      - 完整字段名（含 _）在 query 中出现: +4
      - 短字段名（品牌/型号/价格）精确命中: +4
    L2 关键词匹配:
      - 字段名关键词命中: +3
      - 表名中文部分命中: +2
    L3 语义匹配:
      - 聚合意图 + 数值字段: +2
      - 优先语义词双向命中: +2
      - 样例值命中（型号/品牌名）: +3

    Args:
        question: 标准化后的 query
        candidates: 候选字段列表，每个含 {table, field, type}
        schema_info: 可选，用于查样例值

    Returns:
        按 score 降序排列的字段列表
    """
    q_lower = question.lower()

    # 意图检测
    has_aggregation = any(w in question for w in [
        '平均', '统计', '总计', '总和', '分组', '多少款', '多少种', '数量',
        '最高', '最大', '最多', '最低', '最小', '最少',
        '降序', '升序', '排序', '排名',
    ])
    has_ordering = any(w in question for w in ['降序', '升序', '排序', '排名', '从低到高', '从高到低'])

    scored: list[dict] = []
    for ref in candidates:
        score = 0
        field_name = ref["field"]
        field_lower = field_name.lower()
        table_lower = ref["table"].lower()

        # === L1: 精确匹配 ===
        # 完整字段名（包含 _）在 query 中 → 高置信度
        if '_' in field_name and field_lower in q_lower:
            score += 5
        # 短字段名（无 _）精确命中 → 高置信度（如"品牌""型号""颜色"）
        elif '_' not in field_name and len(field_name) >= 2 and field_name in question:
            score += 5
        else:
            # 字段名各部分命中
            field_parts = re.split(r'[_]+', field_lower)
            for part in field_parts:
                if len(part) >= 2 and part in q_lower:
                    score += 3
                    break  # 只加一次

        # === L2: 表名匹配 ===
        table_cn = _extract_chinese(table_lower)
        if len(table_cn) >= 2 and table_cn in q_lower:
            score += 2

        # === L3: 语义匹配 ===
        # 聚合意图 + 数值字段
        if has_aggregation and ref["type"].upper() in ("INTEGER", "REAL", "FLOAT", "NUMERIC"):
            score += 2

        # 排序意图 + 数值字段
        if has_ordering and ref["type"].upper() in ("INTEGER", "REAL", "FLOAT", "NUMERIC"):
            score += 1

        # 优先语义词双向命中
        priority_tokens = ["价格", "销量", "评分", "重量", "电池", "续航",
                          "噪音", "功率", "刷新率", "分辨率", "容量"]
        for pt in priority_tokens:
            if pt in field_lower and pt in q_lower:
                score += 2
                break

        # === L4: 样例值匹配 ===
        if schema_info:
            sample_values = _get_sample_values(schema_info, ref["table"], field_name)
            for sv in sample_values:
                if len(sv) >= 2 and sv in question:
                    score += 3
                    break

        scored.append({**ref, "score": score})

    # 按分数降序，分数相同按字段名长度升序（短名优先 → 品牌/型号 排前面）
    scored.sort(key=lambda x: (-x["score"], len(x["field"])))

    return scored


def _get_sample_values(schema_info: dict, table: str, field: str) -> list[str]:
    """从 schema_info 中获取字段样例值。"""
    try:
        table_info = schema_info.get("tables", {}).get(table, {})
        for col in table_info.get("columns", []):
            if col.get("name") == field:
                return col.get("sample_values", [])
    except Exception:
        pass
    return []


# ========== Few-shot 示例选择 ==========

def select_fewshot_examples(
    question: str,
    candidate_pool: list[dict],
    top_k: int = 3
) -> list[dict]:
    """
    从候选池中选取与当前 question 最相似的 few-shot 示例。

    相似度 = 共享关键词数量 / 候选 query 长度

    Args:
        question: 当前 query
        candidate_pool: [{"query": "...", "sql": "..."}, ...]
        top_k: 返回示例数

    Returns:
        最相似的 top_k 个示例 [{query, sql}, ...]
    """
    if not candidate_pool:
        return []

    q_chars = set(question)

    scored = []
    for item in candidate_pool:
        c_query = item.get("query", "")
        if not c_query:
            continue
        c_chars = set(c_query)
        # Jaccard 相似度
        intersection = len(q_chars & c_chars)
        union = len(q_chars | c_chars)
        similarity = intersection / max(union, 1)
        scored.append((similarity, item))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]


def retrieve_schema_context(
    question: str,
    schema_info: dict,
    alias_map: dict,
    inverted_index: dict,
    top_k_fields: int = 20
) -> dict:
    """
    综合哈希表和倒排索引，返回和问题最相关的 schema 上下文。

    流程：
    1. 预处理 question
    2. 从 alias_map 做短语级匹配 → 候选字段
    3. 从 inverted_index 做分词级匹配 → 补充候选
    4. 合并去重 → 打分排序 → 取 top-k
    5. 返回结构化上下文

    Args:
        question: 原始用户问题
        schema_info: 数据库结构
        alias_map: 别名哈希表
        inverted_index: 倒排索引
        top_k_fields: 返回字段数上限

    Returns:
        {
            "tables": [...],           # 相关表列表
            "fields": [...],           # 字段 + 分数，按分数降序
            "matched_keywords": [...], # 命中的关键词
            "numeric_conditions": [...], # 数值条件
        }
    """
    # Step 1: 预处理
    normalized = normalize_question(question)

    # Step 2: 短语级匹配（alias_map）
    phrase_matches = _extract_keywords_from_question(normalized, alias_map)
    matched_keywords = list(phrase_matches.keys())

    # Step 3: 收集候选字段
    seen: set[tuple[str, str]] = set()
    candidates: list[dict] = []

    # 从 alias_map 收集
    for kw in matched_keywords:
        if kw in alias_map:
            for ref in alias_map[kw]:
                key = (ref["table"], ref["field"])
                if key not in seen:
                    seen.add(key)
                    candidates.append({
                        "table": ref["table"],
                        "field": ref["field"],
                        "type": ref.get("type", "TEXT"),
                        "match_source": kw,  # 记录命中关键词
                    })

    # Step 4: 从 inverted_index 补充（分词级）
    token_matches = _extract_keywords_from_question(normalized, inverted_index)
    for kw in token_matches:
        if kw not in phrase_matches and kw in inverted_index:  # 避免重复
            if kw not in matched_keywords:
                matched_keywords.append(kw)
            for ref in inverted_index[kw]:
                key = (ref["table"], ref["field"])
                if key not in seen:
                    seen.add(key)
                    candidates.append({
                        "table": ref["table"],
                        "field": ref["field"],
                        "type": ref.get("type", "TEXT"),
                        "match_source": kw,
                    })

    # Step 5: 打分排序
    ranked = rank_fields(normalized, candidates, schema_info)

    # === 必要列保护：确保核心列不被遗漏 ===
    # 对每个出现在 top tables 中的表，如果 品牌/型号/价格 列在候选但不在前排，提上来
    top_table_set = set()
    for f in ranked[:top_k_fields]:
        top_table_set.add(f["table"])

    essential_cols = {"品牌", "型号", "价格_元", "品牌名称", "型号名称"}
    boosted: list[dict] = []
    rest: list[dict] = []
    for f in ranked:
        if f["table"] in top_table_set and f["field"] in essential_cols and f["score"] < 3:
            f["score"] = max(f["score"], 3)  # 确保不低于 3
            boosted.append(f)
        else:
            rest.append(f)

    # 合并：提升后的必要列 + 其余按原分数排序
    ranked = boosted + rest
    ranked.sort(key=lambda x: (-x["score"], len(x["field"])))

    # 取 top-k
    top_fields = ranked[:top_k_fields]

    # 收集相关表
    tables = list(dict.fromkeys(f["table"] for f in top_fields))

    # 提取数值条件
    numeric_conditions = _extract_numbers_from_question(normalized)

    return {
        "tables": tables,
        "fields": top_fields,
        "matched_keywords": matched_keywords,
        "numeric_conditions": numeric_conditions,
    }


# ========== 查询缓存 ==========

def get_cached_sql(question: str, cache: dict) -> str | None:
    """
    从缓存中读取 SQL。O(1)。

    Args:
        question: 标准化后的 query
        cache: {normalized_question: sql}

    Returns:
        缓存的 SQL，或 None
    """
    key = normalize_question(question)
    return cache.get(key)


def update_sql_cache(question: str, sql: str, cache: dict) -> None:
    """
    将新生成的 SQL 写入缓存。

    Args:
        question: 标准化后的 query
        sql: 生成的 SQL
        cache: 缓存字典（会被原地修改）
    """
    key = normalize_question(question)
    cache[key] = sql


# ========== 向量索引（增强模块留空） ==========

def build_vector_index(schema_docs: list[dict]) -> object:
    """
    构建字段描述或示例 SQL 的向量索引。
    最小版本可暂不实现。
    """
    raise NotImplementedError("Vector index is an optional enhancement module")


def retrieve_by_vector(question: str, vector_index: object, top_k: int = 5) -> list[dict]:
    """
    使用语义相似度检索相关字段或历史样例。
    最小版本可暂不实现。
    """
    raise NotImplementedError("Vector index is an optional enhancement module")


# ========== 内部辅助 ==========

def _extract_chinese(s: str) -> str:
    """从字符串中提取中文部分。"""
    return ''.join(c for c in s if '一' <= c <= '鿿')


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import DB_PATH, DATA_DIR, MAX_SCHEMA_FIELDS
    from src.schema_parser import parse_sqlite_schema
    from src.index_builder import build_all_indexes, load_index

    # 加载或构建索引
    processed = DATA_DIR / "processed"
    alias_path = processed / "alias_map.json"
    inverted_path = processed / "inverted_index.json"

    if alias_path.exists() and inverted_path.exists():
        print("Loading cached indexes...")
        alias_map = load_index(str(alias_path))
        inverted_index = load_index(str(inverted_path))
    else:
        print("Building indexes...")
        schema_info = parse_sqlite_schema(str(DB_PATH))
        indexes = build_all_indexes(schema_info, output_dir=str(processed))
        alias_map = indexes["alias_map"]
        inverted_index = indexes["inverted_index"]

    schema_info = parse_sqlite_schema(str(DB_PATH))

    # 测试检索
    test_queries = [
        "联想 ThinkBook 14 的当前价格是多少？",
        "电池容量大于 5000mAh 的手机有哪些？",
        "按品牌统计手机的平均价格。",
        "查询月销量大于 5000 且好评率高于 95% 的商品。",
        "查询价格在 5000 到 10000 元之间、好评率大于 95%、高性价比的笔记本电脑。",
        "哪些空调使用R32冷媒、制冷量在3500W以上，而且支持语音控制和睡眠模式？",
        "有没有压缩机保修10年以上、支持WiFi控制和定时功能的全直流变频空调？",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print(f"{'='*60}")
        result = retrieve_schema_context(
            q, schema_info, alias_map, inverted_index, top_k_fields=MAX_SCHEMA_FIELDS
        )
        print(f"  Tables: {result['tables']}")
        print(f"  Matched keywords: {result['matched_keywords'][:10]}")
        print(f"  Top fields:")
        for f in result["fields"][:8]:
            print(f"    [{f['table']}] {f['field']} (type={f['type']}, score={f['score']})")
        if result["numeric_conditions"]:
            print(f"  Numeric conditions: {result['numeric_conditions']}")
