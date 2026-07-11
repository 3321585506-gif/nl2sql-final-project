"""
Unified LLM client for online, OpenAI-compatible, and local models.

Owner: B
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str | None = None):
        self.provider = (provider or "").strip().lower()
        self.model = model
        self.api_key = api_key or self._resolve_api_key()

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 256) -> str:
        """
        Generate text from a prompt.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        if self.provider in {"mock", "offline", "dummy"}:
            return "SELECT 1;"
        if self.provider in {"openai", "deepseek", "openai-compatible"}:
            return self._generate_openai_compatible(prompt, temperature, max_tokens)
        if self.provider == "local":
            return self._generate_local(prompt, temperature, max_tokens)
        raise ValueError(f"unsupported LLM provider: {self.provider}")

    def _resolve_api_key(self) -> str | None:
        if self.provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        return os.getenv("OPENAI_API_KEY")

    def _resolve_openai_base_url(self) -> str | None:
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            return base_url
        if self.provider == "deepseek":
            return "https://api.deepseek.com/v1"
        return None

    def _generate_openai_compatible(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for provider='openai' or 'openai-compatible'; "
                "DEEPSEEK_API_KEY or OPENAI_API_KEY is required for provider='deepseek'"
            )
        base_url = self._resolve_openai_base_url()
        try:
            from openai import OpenAI
        except ImportError:
            return self._generate_openai_http(prompt, temperature, max_tokens, base_url)

        client_kwargs = {"api_key": self.api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        request_kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = self._create_chat_completion(client, request_kwargs)
        return response.choices[0].message.content or ""

    def _create_chat_completion(self, client, request_kwargs: dict):
        while True:
            try:
                return client.chat.completions.create(**request_kwargs)
            except Exception as exc:
                message = str(exc)
                if "max_tokens" in message and "max_completion_tokens" in message:
                    request_kwargs = dict(request_kwargs)
                    token_limit = request_kwargs.pop("max_tokens", 256)
                    request_kwargs["max_completion_tokens"] = token_limit
                    continue
                if "temperature" in message and "temperature" in request_kwargs:
                    request_kwargs = dict(request_kwargs)
                    request_kwargs.pop("temperature", None)
                    continue
                raise

    def _generate_openai_http(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        base_url: str | None,
    ) -> str:
        api_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise RuntimeError(f"OpenAI-compatible response has no choices: {data}")
        message = choices[0].get("message", {})
        return message.get("content") or choices[0].get("text") or ""

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
