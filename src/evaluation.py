"""
在本地测试集上评估 SQL 准确率、执行结果一致率和延迟得分。

负责人：A

评分指标（比赛规则）：
- EM (Exact Match): 预测 SQL 与标准 SQL 完全匹配的比例 × 100%
- LS (Latency Score): 延迟得分，按分段线性函数计算
- Final Score = EM × 0.8 + LS × 0.2

延迟得分公式：
  t ≤ 0.5s:         score = 1.0
  0.5s < t ≤ 1.0s:  score = 1.0 - 0.5 × (t - 0.5)
  1.0s < t ≤ 2.0s:  score = 0.5 - 0.25 × (t - 1.0)
  t > 2.0s:          score = 0
"""

import json
import re
import sqlite3
from pathlib import Path


# ========== SQL 归一化 ==========

def _normalize_sql_for_compare(sql: str) -> str:
    """
    归一化 SQL 以进行准确比较。

    - 去除首尾空白
    - 统一多个空格为单个
    - 去除末尾分号
    - 关键字转小写（但不影响中文列名）
    - 去除注释
    """
    if not sql:
        return ""
    s = sql.strip()
    s = re.sub(r'\s+', ' ', s)
    s = s.rstrip(';').strip()
    s = re.sub(r'--.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)
    # 仅对 SQL 关键字做小写归一化（不碰中文/列名）
    keywords = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'JOIN', 'ON',
                'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'AS', 'IN',
                'NOT', 'NULL', 'IS', 'BETWEEN', 'LIKE', 'DISTINCT',
                'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'ASC', 'DESC',
                'LEFT', 'RIGHT', 'INNER', 'OUTER', 'WITH', 'UNION']
    for kw in keywords:
        s = re.sub(rf'\b{kw}\b', kw.lower(), s, flags=re.IGNORECASE)
    return s


# ========== 准确率 ==========

def exact_match_accuracy(pred_sqls: list[str], gold_sqls: list[str]) -> float:
    """
    计算 SQL 字符串完全匹配准确率。

    归一化后逐条比较，完全一致才算正确。

    Args:
        pred_sqls: 预测 SQL 列表
        gold_sqls: 标准 SQL 列表

    Returns:
        EM 准确率 (0.0 ~ 1.0)
    """
    if not pred_sqls or not gold_sqls:
        return 0.0

    correct = 0
    for pred, gold in zip(pred_sqls, gold_sqls):
        if _normalize_sql_for_compare(pred) == _normalize_sql_for_compare(gold):
            correct += 1

    return correct / len(pred_sqls)


def execution_match_accuracy(
    pred_sqls: list[str],
    gold_sqls: list[str],
    db_path: str
) -> float:
    """
    计算执行结果一致率（比 EM 更可靠）。

    对每条 (pred_sql, gold_sql)，分别在数据库中执行，比较结果是否相同。
    结果比较：行数相同 + 每行数据相同（排序无关）。

    Args:
        pred_sqls: 预测 SQL 列表
        gold_sqls: 标准 SQL 列表
        db_path: SQLite 数据库路径

    Returns:
        执行一致率 (0.0 ~ 1.0)
    """
    if not pred_sqls or not gold_sqls:
        return 0.0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    correct = 0
    total = 0

    for pred, gold in zip(pred_sqls, gold_sqls):
        if not pred or not gold:
            total += 1
            continue

        try:
            # 执行标准 SQL
            cursor.execute(gold)
            gold_rows = _normalize_rows(cursor.fetchall(), cursor.description)

            # 执行预测 SQL
            cursor.execute(pred)
            pred_rows = _normalize_rows(cursor.fetchall(), cursor.description)

            if gold_rows == pred_rows:
                correct += 1
        except Exception:
            pass  # 执行失败算不匹配

        total += 1

    conn.close()
    return correct / max(total, 1)


def _normalize_rows(rows: list, description) -> set:
    """
    将查询结果归一化为可比较的 set of frozenset。
    每行转为 frozenset of (col_name, str(value))。
    """
    if not rows or not description:
        return frozenset()

    col_names = [d[0] for d in description]
    normalized = set()
    for row in rows:
        items = tuple(
            (col_names[i], str(row[i]) if row[i] is not None else "NULL")
            for i in range(len(row))
        )
        normalized.add(items)
    return frozenset(normalized)


# ========== 延迟得分 ==========

def latency_score(t: float) -> float:
    """
    根据比赛规则计算单条样本延迟得分。

    得分函数（分段线性）：
      t ≤ 0.5  → 1.0
      0.5 < t ≤ 1.0 → 1.0 - 0.5 × (t - 0.5)
      1.0 < t ≤ 2.0 → 0.5 - 0.25 × (t - 1.0)
      t > 2.0  → 0.0

    Args:
        t: 单条样本延迟（秒）

    Returns:
        延迟得分 (0.0 ~ 1.0)
    """
    if t <= 0.5:
        return 1.0
    elif t <= 1.0:
        return 1.0 - 0.5 * (t - 0.5)
    elif t <= 2.0:
        return max(0.0, 0.5 - 0.25 * (t - 1.0))
    else:
        return 0.0


def average_latency_score(latencies: list[float]) -> float:
    """
    计算平均延迟得分 LS。

    Args:
        latencies: 每条样本的延迟（秒）

    Returns:
        LS = Σ latency_score(t_i) / N
    """
    if not latencies:
        return 0.0
    return sum(latency_score(t) for t in latencies) / len(latencies)


# ========== 总分 ==========

def final_score(em: float, ls: float) -> float:
    """
    初赛总分：Score = EM × 0.8 + LS × 0.2

    Args:
        em: EM 准确率 (0.0 ~ 1.0)
        ls: 平均延迟得分 (0.0 ~ 1.0)

    Returns:
        总分 (0.0 ~ 1.0)
    """
    return em * 0.8 + ls * 0.2


# ========== 综合评估 ==========

def evaluate_predictions(
    predictions_file: str,
    validation_file: str,
    db_path: str,
) -> dict:
    """
    综合评估：读取预测 JSON 和验证集，计算全部指标。

    Args:
        predictions_file: 预测结果 JSON 文件路径
        validation_file: 验证集 JSONL 文件路径（含 ground truth SQL）
        db_path: SQLite 数据库路径

    Returns:
        {
            "em": 0.85,
            "exec_match": 0.90,
            "ls": 0.95,
            "final": 0.87,
            "total_samples": 200,
            "latency_stats": {"avg": 0.3, "max": 1.5, "min": 0.1},
            "score_distribution": {...}
        }
    """
    # 读取预测结果
    with open(predictions_file, "r", encoding="utf-8") as f:
        pred_data = json.load(f)

    # 读取验证集
    gold_records = _load_jsonl(validation_file)

    # 按 id 对齐（如果预测结果无 id，按顺序对齐）
    pred_map = {r.get("id", f"Q{i+1:04d}"): r for i, r in enumerate(pred_data.get("results", []))}
    gold_map = {r.get("id", f"Q{i+1:04d}"): r for i, r in enumerate(gold_records)}

    # 只评估两个集合共有的样本
    common_ids = sorted(set(pred_map.keys()) & set(gold_map.keys()))
    print(f"Evaluating {len(common_ids)} samples (pred: {len(pred_map)}, gold: {len(gold_map)})")

    pred_sqls: list[str] = []
    gold_sqls: list[str] = []
    latencies: list[float] = []

    for qid in common_ids:
        pred_sqls.append(pred_map[qid].get("predicted_sql", ""))
        gold_sqls.append(gold_map[qid].get("sql", ""))
        # 解析延迟
        lat_str = pred_map[qid].get("lantancy", pred_map[qid].get("latency", "0s"))
        lat_val = _parse_latency(lat_str)
        latencies.append(lat_val)

    # 计算指标
    em = exact_match_accuracy(pred_sqls, gold_sqls)
    exec_match = execution_match_accuracy(pred_sqls, gold_sqls, db_path)
    ls = average_latency_score(latencies)
    total = final_score(em, ls)

    # 统计延迟
    latency_avg = sum(latencies) / max(len(latencies), 1)

    return {
        "em": round(em, 4),
        "exec_match": round(exec_match, 4),
        "ls": round(ls, 4),
        "final": round(total, 4),
        "total_samples": len(common_ids),
        "latency_stats": {
            "avg": round(latency_avg, 3),
            "max": round(max(latencies), 3) if latencies else 0,
            "min": round(min(latencies), 3) if latencies else 0,
        },
        "pred_sqls": pred_sqls,
        "gold_sqls": gold_sqls,
        "latencies": latencies,
    }


# ========== 报告输出 ==========

def print_evaluation_report(result: dict) -> None:
    """
    格式化打印评估报告。
    """
    print("\n" + "=" * 60)
    print("  EVALUATION REPORT")
    print("=" * 60)
    print(f"  Total samples evaluated: {result['total_samples']}")
    print()
    print(f"  EM  (Exact Match):      {result['em']:.2%}")
    print(f"  EX  (Execution Match):  {result['exec_match']:.2%}")
    print(f"  LS  (Latency Score):    {result['ls']:.4f}")
    print(f"  ─────────────────────────────")
    print(f"  FINAL SCORE:            {result['final']:.4f}")
    print(f"  (EM × 0.8 + LS × 0.2)")
    print()
    print(f"  Latency Stats:")
    stats = result["latency_stats"]
    print(f"    Avg: {stats['avg']:.3f}s")
    print(f"    Max: {stats['max']:.3f}s")
    print(f"    Min: {stats['min']:.3f}s")
    print()

    # 延迟分布
    latencies = result.get("latencies", [])
    if latencies:
        buckets = {"< 0.5s": 0, "0.5-1.0s": 0, "1.0-2.0s": 0, "> 2.0s": 0}
        for t in latencies:
            if t <= 0.5:
                buckets["< 0.5s"] += 1
            elif t <= 1.0:
                buckets["0.5-1.0s"] += 1
            elif t <= 2.0:
                buckets["1.0-2.0s"] += 1
            else:
                buckets["> 2.0s"] += 1
        print(f"  Latency Distribution:")
        for label, count in buckets.items():
            pct = count / len(latencies) * 100
            bar = "█" * int(pct / 5)
            print(f"    {label:>10s}: {count:4d} ({pct:5.1f}%) {bar}")
    print("=" * 60)


# ========== 辅助函数 ==========

def _load_jsonl(path: str) -> list[dict]:
    """读取 JSONL 文件。"""
    records = []
    p = Path(path)
    if not p.exists():
        print(f"  Warning: file not found: {path}")
        return records
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _parse_latency(lat_str: str) -> float:
    """解析 '1.35s' / '0.02s' 格式的延迟字符串。"""
    try:
        return float(lat_str.replace("s", "").strip())
    except (ValueError, AttributeError):
        return 0.0


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import OUTPUT_PATH, DB_PATH, PROJECT_ROOT

    # 验证集路径
    validation_file = PROJECT_ROOT / "初赛数据集" / "初赛_验证集 .jsonl"

    print("=" * 50)
    print("Running Evaluation")
    print("=" * 50)

    if not Path(str(OUTPUT_PATH)).exists():
        print(f"\nPredictions file not found: {OUTPUT_PATH}")
        print("Please run the pipeline first: python run.py")
        sys.exit(1)

    if not validation_file.exists():
        print(f"\nValidation file not found: {validation_file}")
        print("Skipping evaluation (no ground truth)")
        sys.exit(0)

    result = evaluate_predictions(
        predictions_file=str(OUTPUT_PATH),
        validation_file=str(validation_file),
        db_path=str(DB_PATH),
    )

    print_evaluation_report(result)

    # 用 mock 模式时提醒
    from src.config import LLM_PROVIDER
    if LLM_PROVIDER == "mock":
        print("\n  NOTE: Using mock LLM (all SQL = 'SELECT 1;')")
        print("  EM/EX scores are expected to be 0%.")
        print("  Switch LLM_PROVIDER to 'openai' for real evaluation.")
