"""
统一封装大模型调用，方便切换在线模型或本地模型。

负责人：B
"""

class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str | None = None):
        raise NotImplementedError

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 256) -> str:
        """
        输入 prompt，返回模型生成文本。
        """
        raise NotImplementedError
