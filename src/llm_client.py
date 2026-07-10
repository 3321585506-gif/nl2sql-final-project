"""
统一封装大模型调用，方便切换在线模型或本地模型。

负责人：B
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import json


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str | None = None):
        self.provider = (provider or "").strip().lower()
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 256) -> str:
        """
        输入 prompt，返回模型生成文本。
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        if self.provider in {"mock", "offline", "dummy"}:
            return "SELECT 1;"
        if self.provider == "openai":
            return self._generate_openai(prompt, temperature, max_tokens)
        if self.provider == "local":
            return self._generate_local(prompt, temperature, max_tokens)
        raise ValueError(f"unsupported LLM provider: {self.provider}")

    def _generate_openai(self, prompt: str, temperature: float, max_tokens: int) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for provider='openai'")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for provider='openai'") from exc

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _generate_local(self, prompt: str, temperature: float, max_tokens: int) -> str:
        endpoint = os.getenv("LOCAL_LLM_ENDPOINT")
        if not endpoint:
            raise RuntimeError("LOCAL_LLM_ENDPOINT is required for provider='local'")

        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"local LLM request failed: {exc}") from exc

        if isinstance(data, dict):
            for key in ("text", "response", "content", "generated_text"):
                if key in data:
                    return str(data[key])
            choices = data.get("choices")
            if choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict) and "content" in message:
                        return str(message["content"])
                    if "text" in first:
                        return str(first["text"])
        return str(data)
