# 基于哈希索引、倒排索引与图搜索的商品问答 NL2SQL 系统

> 数据结构与算法课程 Final Project  
> 比赛方向：百度智能云客悦杯：大模型挑战赛——语音客服的商品问答能力优化

## 快速运行

先生成/刷新本地预处理产物：

```powershell
python scripts/build_artifacts.py
```

Mock 模式用于本地快速验证，不调用外部 API：

```powershell
$env:LLM_PROVIDER='mock'
$env:LLM_MODEL='mock'
python run.py --eval --limit 20
```

OpenAI `gpt-5.6-luna` 模式：

```powershell
$env:OPENAI_API_KEY=[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='gpt-5.6-luna'
Remove-Item Env:\OPENAI_BASE_URL -ErrorAction SilentlyContinue
python run.py --eval --limit 20
```

DeepSeek 模式有两种写法，推荐同学直接用第一种：

```powershell
$env:DEEPSEEK_API_KEY='你的 DeepSeek key'
$env:LLM_PROVIDER='deepseek'
$env:LLM_MODEL='deepseek-chat'
python run.py --eval --limit 20
```

也兼容 OpenAI-compatible 写法：

```powershell
$env:OPENAI_API_KEY='你的 DeepSeek key'
$env:OPENAI_BASE_URL='https://api.deepseek.com/v1'
$env:LLM_PROVIDER='openai'
$env:LLM_MODEL='deepseek-chat'
python run.py --eval --limit 20
```

## 当前 V2 实测结果

根据 `v2_luna_eval_20.txt`，当前 V2 结构化优先版本在验证集前 20 条上的真实 `gpt-5.6-luna` 结果为：

| 指标 | 数值 |
|---|---:|
| EM | 25.00% |
| EX | 55.00% |
| LS | 0.2500 |
| Final Score | 0.2500 |
| 平均延迟 | 3.851s |
| rule 路由 | 5 / 20 |
| llm 路由 | 15 / 20 |
