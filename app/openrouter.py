"""Cliente OpenRouter: texto (chat), imagens e vídeo."""

from __future__ import annotations

import base64
import json
import re
import time
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

    # ---------------------------------------------------------------- imagens
    def generate_image(self, model: str, prompt: str, aspect_ratio: str = "9:16") -> tuple[bytes, float]:
        """Gera uma imagem. Usa a Image API e, se não disponível, o chat com modalities."""
        resp = self.client.post(
            f"{BASE_URL}/images",
            headers=_headers(self.api_key),
            json={"model": model, "prompt": prompt, "n": 1, "aspect_ratio": aspect_ratio},
        )
        if resp.status_code < 400:
            body = resp.json()
            data = (body.get("data") or [{}])[0]
            if data.get("b64_json"):
                return base64.b64decode(data["b64_json"]), _cost(body)
            if data.get("url"):
                return self._download(data["url"]), _cost(body)
        elif resp.status_code not in (404, 405, 400, 422):
            _raise_for(resp, f"Imagem ({model})")

        # Fallback: chat completions com saída de imagem
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": aspect_ratio},
            "usage": {"include": True},
        }
        resp = self.client.post(f"{BASE_URL}/chat/completions", headers=_headers(self.api_key), json=payload)
        _raise_for(resp, f"Imagem ({model})")
        body = resp.json()
        try:
            images = body["choices"][0]["message"].get("images") or []
            url = images[0]["image_url"]["url"]
        except (KeyError, IndexError) as exc:
            raise OpenRouterError(f"O modelo {model} não retornou imagem") from exc
        return self._decode_url(url), _cost(body)

    def _decode_url(self, url: str) -> bytes:
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[1])
        return self._download(url)

    def _download(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        r = self.client.get(url, headers=headers, follow_redirects=True)
        _raise_for(r, "Download")
        return r.content

    # ------------------------------------------------------------------ vídeo
    def video_models(self) -> list[dict]:
        resp = self.client.get(f"{BASE_URL}/videos/models", headers=_headers(self.api_key))
        _raise_for(resp, "Modelos de vídeo")
        return resp.json().get("data", [])

    def submit_video(
        self,
        model: str,
        prompt: str,
        first_frame: bytes | None = None,
        duration: int = 4,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        generate_audio: bool = False,
    ) -> str:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "generate_audio": generate_audio,
        }
        if first_frame:
            b64 = base64.b64encode(first_frame).decode()
            payload["frame_images"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                    "frame_type": "first_frame",
                }
            ]
        resp = self.client.post(f"{BASE_URL}/videos", headers=_headers(self.api_key), json=payload)
        _raise_for(resp, f"Vídeo ({model})")
        job_id = resp.json().get("id")
        if not job_id:
            raise OpenRouterError("OpenRouter não retornou o id do vídeo")
        return job_id

    def wait_video(self, job_id: str, timeout: float = 900, interval: float = 15) -> tuple[bytes, float]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self.client.get(f"{BASE_URL}/videos/{job_id}", headers=_headers(self.api_key))
            _raise_for(resp, "Status do vídeo")
            body = resp.json()
            status = body.get("status")
            if status == "completed":
                content = self.client.get(
                    f"{BASE_URL}/videos/{job_id}/content",
                    params={"index": 0},
                    headers=_headers(self.api_key),
                    follow_redirects=True,
                )
                if content.status_code >= 400 and body.get("unsigned_urls"):
                    url = body["unsigned_urls"][0]
                    # só manda a chave quando a URL é da própria API do OpenRouter
                    auth = _headers(self.api_key) if url.startswith(BASE_URL) else None
                    return self._download(url, auth), _cost(body)
                _raise_for(content, "Download do vídeo")
                return content.content, _cost(body)
            if status in ("failed", "cancelled", "expired"):
                raise OpenRouterError(f"Geração de vídeo {status}: {body.get('error') or body}")
            time.sleep(interval)
        raise OpenRouterError("Tempo esgotado esperando o vídeo do OpenRouter")

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
    """Agrupa modelos por tipo de saída e ordena pelo preço (mais barato primeiro)."""
    groups: dict[str, list[dict]] = {"text": [], "image": []}
    for m in models:
        arch = m.get("architecture") or {}
        out = arch.get("output_modalities") or ["text"]
        pricing = m.get("pricing") or {}

        def p(k: str, pricing: dict = pricing) -> float:
            try:
                return float(pricing.get(k) or 0)
            except (TypeError, ValueError):
                return 0.0

        item = {
            "id": m.get("id"),
            "name": m.get("name"),
            "context": m.get("context_length"),
            "prompt_per_m": round(p("prompt") * 1_000_000, 4),
            "completion_per_m": round(p("completion") * 1_000_000, 4),
            "image_price": p("image"),
            "free": (m.get("id") or "").endswith(":free") or (p("prompt") == 0 and p("completion") == 0),
        }
        if "image" in out:
            groups["image"].append(item)
        if "text" in out and "image" not in out:
            groups["text"].append(item)
    for k in groups:
        groups[k].sort(key=lambda x: (not x["free"], x["prompt_per_m"] + x["completion_per_m"]))
    return groups
