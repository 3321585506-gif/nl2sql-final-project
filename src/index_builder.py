"""
构建字段别名哈希表和倒排索引。

负责人：A

两个核心数据结构：

1. alias_map (哈希表)
   - 短语级别的中文别名 → 字段引用列表
   - 用于 retriever 做精确别名匹配
   - 查找复杂度 O(1)

2. inverted_index (倒排索引)
   - 分词级别的关键词 → 字段引用列表
   - 用于 retriever 做多关键词联合检索
   - 支持部分匹配（如 query 含"电池" → 命中性名为"电池容量_mAh"的字段）

索引构建策略：
- 列名拆分：按 '_' 分隔，再按中/英文边界切分
- 中文部分：保留全词 + 生成 bigram（如"电池容量" → "电池容量" + "电池" + "容量"）
- 英文/数字部分：保留原词
- 同义词组：人工补充，解决"售价=价格"这类语义等价
"""

import json
import re
from pathlib import Path


# ========== 内置同义词组 ==========
# 每个 list 内的词互为同义词，都会映射到相同的字段集合

SYNONYM_GROUPS: list[list[str]] = [
    # 价格
    ["价格", "售价", "价钱", "单价", "定价", "官方指导价", "吊牌价",
     "日常销售价", "活动销售价", "券后价", "成交均价", "最低成交价",
     "最高成交价", "采购价", "当前价格", "价格_元"],
    # 销量
    ["销量", "月销量", "累计销量", "当日销量", "销售量", "销售额",
     "月度销量", "年度销量"],
    # 品牌
    ["品牌", "牌子", "厂商", "品牌名称", "处理器品牌", "显卡品牌",
     "压缩机品牌", "电机品牌", "主板品牌"],
    # 型号
    ["型号", "型号名称", "型号编码", "处理器型号", "显卡型号",
     "蓝牙芯片型号", "CPU型号"],
    # 重量
    ["重量", "机身重量", "净重", "产品净重", "整机重量", "室内机重量",
     "室外机重量", "耳机重量", "充电盒重量", "包装重量"],
    # 电池/续航
    ["电池", "电池容量", "续航", "续航时间", "续航里程",
     "耳机续航时长", "充电盒续航时长", "电池容量_mAh", "电池容量_Wh"],
    # 好评/评分
    ["好评", "好评率", "评分", "用户评分", "评价", "正面评价"],
    # 库存
    ["库存", "库存状态", "库存量", "可售库存量", "期末库存量", "期初库存量",
     "是否现货", "现货"],
    # 尺寸
    ["尺寸", "屏幕尺寸", "机身尺寸", "产品尺寸", "室内机尺寸", "室外机尺寸",
     "包装尺寸", "耳机尺寸", "充电盒尺寸"],
    # 颜色
    ["颜色", "机身颜色", "产品颜色", "机箱颜色", "A面颜色", "C面颜色",
     "室内机颜色", "室外机颜色"],
    # 噪音/降噪
    ["噪音", "噪音等级", "降噪", "主动降噪", "降噪深度", "通话降噪",
     "噪音_dB", "降噪深度_dB"],
    # 功率
    ["功率", "额定功率", "制冷功率", "制热功率", "电源功率", "峰值功率",
     "整机功耗", "最大输入功率"],
    # 屏幕
    ["屏幕", "屏幕分辨率", "屏幕刷新率", "屏幕尺寸", "液晶屏",
     "屏幕面板", "屏幕比例", "屏幕亮度", "触控屏", "触摸屏"],
    # 内存
    ["内存", "内存容量", "内存类型", "标配内存", "最大内存", "内存频率",
     "内存插槽"],
    # 硬盘
    ["硬盘", "硬盘容量", "硬盘类型", "固态硬盘", "标配硬盘",
     "硬盘接口", "扩展硬盘"],
    # 显卡
    ["显卡", "显卡型号", "显卡类型", "显存", "显存容量", "独显", "核显"],
    # CPU/处理器
    ["处理器", "CPU", "CPU型号", "CPU品牌", "CPU核心数", "CPU线程数",
     "处理器型号", "处理器品牌", "处理器系列", "处理器核心数"],
    # 摄像头
    ["摄像头", "摄像头像素", "摄像头规格", "红外摄像头"],
    # 蓝牙
    ["蓝牙", "蓝牙版本", "蓝牙功能", "蓝牙芯片"],
    # WiFi/无线
    ["WiFi", "WiFi控制", "WiFi功能", "无线网卡", "无线", "无线协议",
     "无线充电", "无线传输"],
    # 接口
    ["接口", "USB", "USB接口", "HDMI接口", "Type_C", "雷电接口",
     "VGA接口", "音频接口", "RJ45接口", "充电接口"],
    # 材质
    ["材质", "机身材质", "外壳材质", "车架材质", "耳垫材质", "头梁材质"],
    # 能效
    ["能效", "能效等级", "能效比", "能效比_制冷", "能效比_制热"],
    # 空调相关
    ["空调", "空调类型", "变频", "变频类型", "冷媒", "冷媒类型", "R32", "R410A",
     "自清洁", "除湿", "加湿", "制冷", "制热", "制冷量", "制热量",
     "柜机", "壁挂式", "挂机", "安装方式"],
    # 笔记本相关
    ["笔记本", "笔记本电脑", "轻薄本", "游戏本", "产品类型", "产品定位"],
    # 适用面积/场景
    ["适用面积", "适用场景", "适用人群", "使用场景"],
    # 保修/质保
    ["保修", "质保", "保修期", "保修年限", "质保年限", "售后服务"],
    # 上市/发布
    ["上市", "发布", "上市年份", "上市日期", "发布年份"],
]


# ========== 关键词提取 ==========

def _split_column_name(col_name: str) -> list[str]:
    """
    将列名拆分为索引关键词。

    策略：
    1. 按 '_' 切分
    2. 对每个片段，在中英文交界处再切分
    3. 对中文片段（长度 > 1），额外生成 bigram

    示例：
    '电池容量_mAh' → ['电池容量', '电池', '容量', 'mAh', '电池容量_mAh']
    '屏幕刷新率Hz' → ['屏幕刷新率', '屏幕', '刷新率', '刷新', 'Hz', '屏幕刷新率Hz']
    '品牌'          → ['品牌', '品牌']  (去重后只有 ['品牌'])
    """
    tokens: list[str] = []
    english_pattern = re.compile(r'[a-zA-Z0-9]+|[^\x00-\x7F]+')

    # Step 1: 按 '_' 切分
    parts = col_name.split('_')

    for part in parts:
        if not part:
            continue
        # Step 2: 在中英文/数字边界再切分
        sub_parts = english_pattern.findall(part)
        for sp in sub_parts:
            tokens.append(sp)
            # Step 3: 对纯中文且长度 > 1，生成 bigram
            if _is_chinese(sp) and len(sp) >= 2:
                for i in range(len(sp) - 1):
                    tokens.append(sp[i:i + 2])

    # 始终保留完整列名
    tokens.append(col_name)

    # 去重并保持顺序
    seen = set()
    result = []
    for t in tokens:
        tl = t.lower().strip()
        if tl and tl not in seen:
            seen.add(tl)
            result.append(tl)

    return result


def _is_chinese(s: str) -> bool:
    """判断字符串是否全为中文（不含英文/数字/符号）。"""
    return all('一' <= c <= '鿿' or c in '_' for c in s) and any('一' <= c <= '鿿' for c in s)


# ========== 别名哈希表 ==========

def build_alias_map(
    schema_info: dict,
    extra_aliases: dict[str, list[str]] | None = None
) -> dict[str, list[dict]]:
    """
    构建字段别名哈希表。

    对每列：提取关键词 → 映射到该字段引用。
    额外别名：{同义词: [目标关键词列表]}，将同义词也映射到相同字段集合。

    Args:
        schema_info: schema_parser 产出的数据库结构
        extra_aliases: 额外的同义词映射 {别名: [已存在的key]}

    Returns:
        alias_map = {
            "价格": [{"table": "headphones", "field": "价格_元", "type": "INTEGER"}, ...],
            "品牌": [{"table": "headphones", "field": "品牌", "type": "TEXT"}, ...],
            ...
        }
    """
    alias_map: dict[str, list[dict]] = {}

    # Step 1: 从 schema_info 自动构建
    for table_name, table_info in schema_info["tables"].items():
        for col in table_info["columns"]:
            field_ref = {
                "table": table_name,
                "field": col["name"],
                "type": col["type"],
            }

            # 从列名提取关键词
            keywords = _split_column_name(col["name"])
            for kw in keywords:
                alias_map.setdefault(kw, []).append(field_ref)

            # 从表名提取关键词（作为上下文）
            table_keywords = _split_column_name(table_name)
            for tk in table_keywords:
                # 用 "table:" 前缀标记，表示这是表级别的命中
                alias_map.setdefault(tk, []).append(field_ref)

    # Step 2: 应用同义词组（SYNONYM_GROUPS）
    for group in SYNONYM_GROUPS:
        # 收集该组内所有词能命中的字段引用
        merged_refs: list[dict] = []
        seen_refs: set[tuple[str, str]] = set()

        for word in group:
            if word in alias_map:
                for ref in alias_map[word]:
                    key = (ref["table"], ref["field"])
                    if key not in seen_refs:
                        seen_refs.add(key)
                        merged_refs.append(ref)

        # 将该组内所有词都映射到合并后的字段集合
        for word in group:
            alias_map[word] = list(merged_refs)

    # Step 3: 应用外部 extra_aliases
    if extra_aliases:
        for alias, target_keywords in extra_aliases.items():
            merged_refs: list[dict] = []
            seen_refs: set[tuple[str, str]] = set()
            for target_kw in target_keywords:
                if target_kw in alias_map:
                    for ref in alias_map[target_kw]:
                        key = (ref["table"], ref["field"])
                        if key not in seen_refs:
                            seen_refs.add(key)
                            merged_refs.append(ref)
            alias_map[alias] = merged_refs

    # 统计
    print(f"alias_map built: {len(alias_map)} aliases, "
          f"avg {sum(len(v) for v in alias_map.values()) // max(len(alias_map), 1)} refs/alias")

    return alias_map


# ========== 倒排索引 ==========

def build_inverted_index(
    schema_info: dict,
    alias_map: dict
) -> dict[str, list[dict]]:
    """
    构建倒排索引：关键词 → 字段引用列表。

    倒排索引与 alias_map 的区别：
    - alias_map 包含短语级和同义词扩展，用于精确匹配
    - inverted_index 是纯分词索引，用于多关键词检索时的 TF 式打分

    Args:
        schema_info: 数据库结构
        alias_map: 已构建的别名哈希表（用于复用同义词扩展后的结果）

    Returns:
        inverted_index = {
            "电池": [ref1, ref2, ...],
            "容量": [ref1, ref3, ...],
            ...
        }
    """
    inverted_index: dict[str, list[dict]] = {}

    for table_name, table_info in schema_info["tables"].items():
        for col in table_info["columns"]:
            field_ref = {
                "table": table_name,
                "field": col["name"],
                "type": col["type"],
            }

            # 对列名做分词
            keywords = _split_column_name(col["name"])
            for kw in keywords:
                inverted_index.setdefault(kw, []).append(field_ref)

            # 对表名分词
            table_keywords = _split_column_name(table_name)
            for tk in table_keywords:
                inverted_index.setdefault(tk, []).append(field_ref)

    # 也从 alias_map 中提取同义词扩展（但不包含那些过长的 key）
    for alias, refs in alias_map.items():
        # 只索引长度 ≤ 10 的 key，避免将长 query 当作关键词
        if len(alias) <= 10 and alias not in inverted_index:
            inverted_index[alias] = refs

    print(f"inverted_index built: {len(inverted_index)} tokens")

    return inverted_index


def build_value_index(schema_catalog: dict) -> dict[str, list[dict]]:
    """
    Build value -> field references index from schema catalog enum/sample values.

    Returns:
        {
            "铝合金": [
                {"table": "electric_vehicle", "field": "车架材质", "value": "铝合金"}
            ]
        }
    """
    value_index: dict[str, list[dict]] = {}
    for table_name, table_info in (schema_catalog or {}).get("tables", {}).items():
        columns = table_info.get("columns", {})
        for column_name, column_info in columns.items():
            values = list(column_info.get("enum_values") or [])
            if not values:
                values = list(column_info.get("sample_values") or [])
            for value in values:
                if value is None:
                    continue
                key = _normalize_value_key(value)
                if not key:
                    continue
                ref = {"table": table_name, "field": column_name, "value": value}
                _append_unique_ref(value_index.setdefault(key, []), ref)
    return value_index


def build_entity_indexes(schema_catalog: dict) -> dict[str, dict]:
    """
    Build brand/model/enum indexes for entity extraction and longest matching.
    """
    brand_index: dict[str, list[dict]] = {}
    model_index: dict[str, list[dict]] = {}
    enum_index: dict[str, list[dict]] = {}

    for table_name, table_info in (schema_catalog or {}).get("tables", {}).items():
        columns = table_info.get("columns", {})
        for column_name, column_info in columns.items():
            role = column_info.get("role")
            enum_values = list(column_info.get("enum_values") or [])
            sample_values = list(column_info.get("sample_values") or [])
            values = enum_values or sample_values
            for value in values:
                key = _normalize_value_key(value)
                if not key:
                    continue
                ref = {"table": table_name, "field": column_name, "value": value}
                if role == "brand":
                    _append_unique_ref(brand_index.setdefault(key, []), ref)
                elif role == "model":
                    _append_unique_ref(model_index.setdefault(key, []), ref)
                if enum_values:
                    _append_unique_ref(enum_index.setdefault(key, []), ref)

    return {
        "brand_index": brand_index,
        "model_index": model_index,
        "enum_index": enum_index,
        "brand_values_by_length": _values_by_length(brand_index),
        "model_values_by_length": _values_by_length(model_index),
    }


# ========== 持久化 ==========

def save_index(index: dict, path: str) -> None:
    """
    将索引保存为 JSON 文件（UTF-8，不转义中文）。

    Args:
        index: alias_map 或 inverted_index
        path: 输出路径
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    print(f"Index saved: {out_path} ({size_kb:.1f} KB)")


def load_index(path: str) -> dict:
    """
    从 JSON 文件加载索引。

    Args:
        path: JSON 索引文件路径

    Returns:
        索引字典
    """
    with open(path, "r", encoding="utf-8") as f:
        index = json.load(f)
    print(f"Index loaded: {path} ({len(index)} entries)")
    return index


def _normalize_value_key(value) -> str:
    return str(value).strip().lower()


def _append_unique_ref(refs: list[dict], ref: dict) -> None:
    key = (ref.get("table"), ref.get("field"), str(ref.get("value")))
    for existing in refs:
        if (existing.get("table"), existing.get("field"), str(existing.get("value"))) == key:
            return
    refs.append(ref)


def _values_by_length(index: dict[str, list[dict]]) -> list[str]:
    return sorted(index.keys(), key=lambda item: (-len(item), item))


# ========== 一键构建 ==========

def build_all_indexes(
    schema_info: dict,
    output_dir: str | None = None,
    extra_aliases: dict[str, list[str]] | None = None
) -> dict[str, dict]:
    """
    一站式构建 alias_map 和 inverted_index，并可选保存到文件。

    Args:
        schema_info: 数据库结构
        output_dir: 索引输出目录（可选）
        extra_aliases: 额外别名词典

    Returns:
        {"alias_map": ..., "inverted_index": ...}
    """
    alias_map = build_alias_map(schema_info, extra_aliases)
    inverted_index = build_inverted_index(schema_info, alias_map)

    indexes = {
        "alias_map": alias_map,
        "inverted_index": inverted_index,
    }

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        save_index(alias_map, str(out / "alias_map.json"))
        save_index(inverted_index, str(out / "inverted_index.json"))

    return indexes


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from src.config import DB_PATH, DATA_DIR
    from src.schema_parser import parse_sqlite_schema

    # 解析 schema
    print("=" * 50)
    print("Step 1: Parse schema")
    print("=" * 50)
    schema_info = parse_sqlite_schema(str(DB_PATH))

    # 构建索引
    print("\n" + "=" * 50)
    print("Step 2: Build indexes")
    print("=" * 50)
    indexes = build_all_indexes(
        schema_info,
        output_dir=str(DATA_DIR / "processed"),
    )

    # 交互式测试
    print("\n" + "=" * 50)
    print("Index Lookup Demo")
    print("=" * 50)

    test_words = ["价格", "品牌", "电池", "噪音", "续航", "屏幕刷新率", "好评"]
    for word in test_words:
        if word in indexes["alias_map"]:
            refs = indexes["alias_map"][word]
            tables = list(set(r["table"] for r in refs))
            print(f"  '{word}' -> {len(refs)} fields across {tables}")
        else:
            print(f"  '{word}' -> NOT FOUND")
