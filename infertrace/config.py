"""Strict configuration and evidence-based capability discovery."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base_url: str = "http://127.0.0.1:8000"
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    collector_url: str = "http://127.0.0.1:8080/events"
    api_key_env: str | None = None
    enabled: bool = True
    sample_rate: float = Field(default=1.0, ge=0, le=1)
    capacity: int = Field(default=1024, ge=1, le=65536)
    batch_size: int = Field(default=64, ge=1, le=256)
    adaptive: bool = False

    @field_validator("base_url", "collector_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        url = urlparse(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("expected HTTP(S) URL without embedded credentials")
        return value.rstrip("/")

    def api_key(self) -> str | None:
        if self.api_key_env:
            key = os.getenv(self.api_key_env)
            if not key:
                raise ValueError("configured API key environment variable is missing")
            return key
        return None


def load_config(path: str | None = None) -> Config:
    configured = path or os.getenv("INFERTRACE_CONFIG")
    return Config.model_validate_json(Path(configured).read_text()) if configured else Config()


def discover(config: Config, *, transport: httpx.BaseTransport | None = None) -> dict[str, object]:
    base = config.base_url if config.base_url.endswith("/v1") else config.base_url + "/v1"
    headers = {}
    if key := config.api_key():
        headers["Authorization"] = f"Bearer {key}"
    result: dict[str, object] = {
        "streaming": "configured-not-probed",
        "engine_tokens": False,
        "engine_phases": "unknown",
        "request_source_patch_required": False,
        "models": [],
        "metrics": False,
    }
    with httpx.Client(timeout=2.0, transport=transport, headers=headers) as client:
        try:
            response = client.get(base + "/models")
            response.raise_for_status()
            models = response.json()["data"]
            result["models"] = [m["id"] for m in models if isinstance(m.get("id"), str)]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            result["models_error"] = "unavailable-or-invalid"
        try:
            response = client.get(config.base_url.removesuffix("/v1") + "/metrics")
            result["metrics"] = response.is_success and "vllm:" in response.text
        except httpx.HTTPError:
            pass
    return result
