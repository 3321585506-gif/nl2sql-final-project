# OpenAI gpt-5.6-luna 实测报告（2026-07-11）

## 结论摘要

本次已经确认本机可以通过 OpenAI API 调用 `gpt-5.6-luna`，并完成验证集前 20 条真实评测。

| 项目 | 结果 |
|---|---:|
| 模型 | `openai / gpt-5.6-luna` |
| 样本数 | 20 |
| EM | 0.00% |
| EX | 35.00% |
| LS | 0.0000 |
| Final Score | 0.0000 |
| 平均延迟 | 4.460s |
| 最大延迟 | 8.510s |
| 最小延迟 | 2.740s |
| 延迟 > 2s | 20 / 20 |

按当前 `src/evaluation.py` 的比赛公式：

```text
Final Score = EM * 0.8 + LS * 0.2
```

虽然 EX 达到 35%，说明部分 SQL 的执行结果已经能对上，但 EM 为 0 且全部样本延迟超过 2 秒，所以 LS 为 0，最终分仍为 0。

## 本次修复

为支持 `gpt-5.6-luna`，修复了以下兼容问题：

1. `src/llm_client.py`：当模型不支持 `max_tokens` 时，自动切换为 `max_completion_tokens`。
2. `src/llm_client.py`：当模型不支持显式 `temperature=0.0` 时，自动移除 `temperature`，使用模型默认值。
3. `src/sql_generator.py`：主生成调用的 token 上限从 256 提高到 1024，避免新模型把 completion 预算用于内部推理后输出空 SQL。
4. `run.py --eval`：标题现在显示实际环境变量中的模型，例如 `openai / gpt-5.6-luna`，不再误显示配置文件默认值 `deepseek-chat`。

最小调用验证：

```text
model=gpt-5.6-luna
SELECT 1;
```

## 评测命令

```powershell
$env:OPENAI_API_KEY=[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='gpt-5.6-luna'
Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
python run.py --eval --limit 20
```

## 两轮对比

| 版本 | 主生成 token 上限 | EM | EX | LS | Final | 平均延迟 | 说明 |
|---|---:|---:|---:|---:|---:|---:|---|
| luna 初跑 | 256 | 0.00% | 25.00% | 0.0000 | 0.0000 | 3.908s | 多条预测 SQL 为空 |
| luna 调整后 | 1024 | 0.00% | 35.00% | 0.0000 | 0.0000 | 4.460s | 空 SQL 消失，EX 提升，但延迟上升 |

## 主要样本观察

| 样本 | 现象 | 影响 |
|---:|---|---|
| Q0001 | SQL 语义正确，但模型给字段和表名加了双引号；EM 仍不匹配 | EX 可能正确，EM 失败 |
| Q0002 | 多表 JOIN 能生成，但输出较长且与标准 SQL 写法不同 | EM 失败，EX 取决于执行结果 |
| Q0005 | 把 `触摸屏 = '是'` 写成 `触摸屏 = '有'` | 条件值误判 |
| Q0006 | 漏掉型号过滤，退化为 `LIMIT 1` | 执行结果大概率错误 |
| Q0011 | 使用不存在/不匹配字段 `散热方式`，标准答案为 `散热器类型` | schema/语义映射错误 |
| Q0014 | 把品牌拼进型号值：`格力KFR-...`，标准只用 `KFR-...` | 条件值抽取错误 |

## 性能判断

`gpt-5.6-luna` 的真实调用已经可用，生成质量比 fallback 明显好，EX 从之前失败调用的 0% 提升到 35%。但当前比赛公式更看重 EM 和延迟：

- EM 仍为 0，说明 SQL 字符串格式、字段顺序、条件写法和标准答案差距较大。
- 平均延迟 4.460s，超过 2 秒阈值，导致 LS 为 0。
- 使用 1024 token 能减少空输出，但进一步拉高延迟。

当前 `luna` 更适合用作质量对照或离线分析，不适合作为最终提交的低延迟方案。若按比赛得分优化，下一步应优先考虑：

1. 将生成链路拆成“快速规则/检索优先 + LLM 兜底”，减少每题必调大模型。
2. 对 SQL 做规范化后处理，例如去掉无必要引号、统一字段顺序、修正常见值映射。
3. 强化实体值抽取，特别是品牌和型号拆分、中文品牌到英文品牌映射、`是/有` 等布尔值同义映射。
4. 评估更快模型或本地缓存策略，把平均延迟压到 2 秒以内。

## 后续 V2 结构化优先结果

在继续引入预处理产物、QueryIR 嵌套条件、SQLCompiler 格式调整和 5 条规则路由后，前 20 条真实 `gpt-5.6-luna` 评测已经提升为：

| 指标 | luna 调整后 | V2 结构化优先 |
|---|---:|---:|
| EM | 0.00% | 25.00% |
| EX | 35.00% | 55.00% |
| LS | 0.0000 | 0.2500 |
| Final Score | 0.0000 | 0.2500 |
| 平均延迟 | 4.460s | 3.851s |
| rule 路由 | 0 / 20 | 5 / 20 |
| llm 路由 | 20 / 20 | 15 / 20 |

因此当前可汇报的最新分数应以 `docs/v2_structured_priority_update_2026-07-11.md` 中的 V2 结果为准。
