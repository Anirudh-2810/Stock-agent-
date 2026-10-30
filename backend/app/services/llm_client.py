import logging
import os
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# OmniRoute gateway: OpenAI-compatible, single API key, LLM_API_KEY sourced from
# owner's auth.json (E:\Brain\Second-Brain\auth.json) - never hardcode keys here.
BASE_URL = os.environ.get("LLM_BASE_URL") or "http://localhost:20128/v1"
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "")


class LLMClient:
    def __init__(self):
        self.base_url = BASE_URL.rstrip("/")
        self.api_key = API_KEY
        self.default_model = MODEL
        self._cached_models: Optional[List[str]] = None

    def _headers(self) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return h

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                r.raise_for_status()
                self._cached_models = [
                    m.get("id") for m in r.json().get("data", []) if m.get("id")
                ]
                return True
        except Exception as e:
            logger.warning(f"LLM gateway unavailable at {self.base_url}: {e}")
            return False

    @staticmethod
    def _pick_model(default: str, models: Optional[List[str]]) -> str:
        cand = default
        if models:
            if not cand or not any(cand in m for m in models):
                pref = [
                    m for m in models
                    if any(k in m.lower() for k in ("gpt-4o", "claude", "gemini"))
                ]
                cand = pref[0] if pref else models[0]
        return cand

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> Dict:
        """OpenAI-compatible chat completion via OmniRoute gateway."""
        try:
            model_id = self._pick_model(model or self.default_model, self._cached_models)
            payload = {
                "model": model_id,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
                )
                r.raise_for_status()
                data = r.json()
            return {"available": True, "model": model_id, "content": data["choices"][0]["message"]["content"]}
        except Exception as e:
            logger.warning(f"LLM chat failed: {e}")
            return {"available": False, "error": str(e), "content": None}


llm_client = LLMClient()
