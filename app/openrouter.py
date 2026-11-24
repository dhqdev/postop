"""Cliente OpenRouter: só texto (chat). É a única IA do sistema: escolhe cortes e escreve roteiros."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
HEADERS_EXTRA = {"HTTP-Referer": "https://github.com/dhqdev/postop", "X-Title": "PostOp"}


class OpenRouterError(RuntimeError):
    pass


@dataclass
class ChatResult:
    content: str
    model: str
    cost: float = 0.0


def _headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise OpenRouterError("Configure a API key do OpenRouter em Configurações.")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **HEADERS_EXTRA}


def _raise_for(resp: httpx.Response, what: str) -> None:
    if resp.status_code >= 400:
        try:
            body = resp.json()
            msg = body.get("error", {}).get("message") or json.dumps(body)[:500]
        except Exception:
            msg = resp.text[:500]
        raise OpenRouterError(f"{what}: HTTP {resp.status_code} - {msg}")


def _cost(body: dict) -> float:
    usage = body.get("usage") or {}
    try:
        return float(usage.get("cost") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def parse_json(text: str) -> dict | list:
    """Extrai JSON de uma resposta de LLM (aceita ```json ... ```)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start < 0:
            raise
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


class OpenRouter:
    def __init__(self, api_key: str, timeout: float = 180.0, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------ texto
    def chat(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> ChatResult:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = self.client.post(f"{BASE_URL}/chat/completions", headers=_headers(self.api_key), json=payload)
        if resp.status_code == 400 and json_mode:
            # alguns modelos não aceitam response_format; tenta sem
            payload.pop("response_format", None)
            resp = self.client.post(
                f"{BASE_URL}/chat/completions", headers=_headers(self.api_key), json=payload
            )
        _raise_for(resp, f"Chat ({model})")
        body = resp.json()
        if body.get("error"):
            raise OpenRouterError(f"Chat ({model}): {body['error']}")
        try:
            content = body["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError) as exc:
            raise OpenRouterError(f"Resposta inesperada do modelo {model}") from exc
        return ChatResult(content=content, model=body.get("model", model), cost=_cost(body))

    def chat_json(self, models: list[str], system: str, user: str) -> tuple[dict | list, float, str]:
        """Tenta cada modelo até conseguir um JSON válido."""
        errors = []
        total = 0.0
        for model in [m for m in models if m]:
            for _attempt in range(2):
                try:
                    r = self.chat(
                        model,
                        [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        json_mode=True,
                    )
                    total += r.cost
                    return parse_json(r.content), total, r.model
                except (OpenRouterError, json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"{model}: {exc}")
        raise OpenRouterError("Nenhum modelo de texto respondeu: " + " | ".join(errors)[-1500:])

    # -------------------------------------------------------------- utilitários
    def key_info(self) -> dict:
        resp = self.client.get(f"{BASE_URL}/key", headers=_headers(self.api_key))
        _raise_for(resp, "Chave")
        return resp.json().get("data", {})

    def list_models(self) -> list[dict]:
        resp = self.client.get(f"{BASE_URL}/models", headers=_headers(self.api_key))
        _raise_for(resp, "Modelos")
        return resp.json().get("data", [])


def summarize_models(models: list[dict]) -> dict[str, list[dict]]:
    """Modelos de texto ordenados pelo preço (grátis e mais baratos primeiro)."""
    text: list[dict] = []
    for m in models:
        arch = m.get("architecture") or {}
        out = arch.get("output_modalities") or ["text"]
        if "text" not in out or "image" in out:
            continue
        pricing = m.get("pricing") or {}

        def p(k: str, pricing: dict = pricing) -> float:
            try:
                return float(pricing.get(k) or 0)
            except (TypeError, ValueError):
                return 0.0

        text.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "context": m.get("context_length"),
                "prompt_per_m": round(p("prompt") * 1_000_000, 4),
                "completion_per_m": round(p("completion") * 1_000_000, 4),
                "free": (m.get("id") or "").endswith(":free") or (p("prompt") == 0 and p("completion") == 0),
            }
        )
    text.sort(key=lambda x: (not x["free"], x["prompt_per_m"] + x["completion_per_m"]))
    return {"text": text}
