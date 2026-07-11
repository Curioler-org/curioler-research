from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        provider = self.config.provider.lower()
        if provider == "openrouter":
            return self._openai_compatible(
                "https://openrouter.ai/api/v1/chat/completions",
                os.environ["OPENROUTER_API_KEY"],
                self.config.model or "openai/gpt-4.1-mini",
                system_prompt,
                user_prompt,
            )
        if provider == "openai":
            return self._openai_compatible(
                "https://api.openai.com/v1/chat/completions",
                os.environ["OPENAI_API_KEY"],
                self.config.model or "gpt-4.1-mini",
                system_prompt,
                user_prompt,
            )
        if provider == "anthropic":
            return self._anthropic(
                os.environ["ANTHROPIC_API_KEY"],
                self.config.model or "claude-3-5-haiku-latest",
                system_prompt,
                user_prompt,
            )
        raise ValueError(f"Unsupported AI provider: {self.config.provider}")

    def _openai_compatible(self, url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if "openrouter.ai" not in url:
            payload["response_format"] = {"type": "json_object"}
        data = self._post_json(url, api_key, payload)
        return self._parse_json_content(data["choices"][0]["message"]["content"])

    def _anthropic(self, api_key: str, model: str, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "model": model,
            "max_tokens": 4000,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return self._parse_json_content(data["content"][0]["text"])

    def _post_json(self, url: str, api_key: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {detail}") from exc

    def _parse_json_content(self, content: str) -> dict:
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
