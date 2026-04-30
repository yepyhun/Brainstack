from __future__ import annotations

from dataclasses import dataclass
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from typing import Any, Callable


def _text(value: Any) -> str:
    return str(value or "").strip()


def _message_content(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return _text(content)


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    else:
        prompt = int(getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0)
        completion = int(
            getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0
        )
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


def _response_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if choices:
        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None and isinstance(choice, dict):
            message = choice.get("message")
        return _message_content(message)
    return _text(getattr(response, "output_text", ""))


@dataclass
class HermesManagedLLMProxy:
    """OpenAI-wire local proxy backed by Hermes' own provider router.

    Hindsight can only call OpenAI-compatible HTTP providers. Hermes-managed
    providers can be Codex Responses, API-key providers, custom endpoints, or
    future provider routes. This proxy keeps Hindsight local while delegating
    model/auth/provider handling to Hermes instead of hardcoding a model.
    """

    model: str
    provider: str = "main"
    host: str = "127.0.0.1"
    port: int = 0
    timeout_seconds: float = 180.0
    client_resolver: Callable[[str, str], tuple[Any, str | None]] | None = None

    def __post_init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Hermes-managed LLM proxy is not started")
        return f"http://{self.host}:{self._server.server_port}/v1"

    def start(self) -> "HermesManagedLLMProxy":
        if self._server is not None:
            return self
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "BrainstackHermesLLMProxy/1"

            def log_message(self, _: str, *args: Any) -> None:
                return

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path.rstrip("/") in {"/healthz", "/v1/healthz"}:
                    self._send_json(HTTPStatus.OK, {"status": "ok"})
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                if self.path.rstrip("/") != "/v1/chat/completions":
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                    response = proxy.complete(payload)
                except Exception as exc:
                    self._send_json(
                        HTTPStatus.BAD_GATEWAY,
                        {"error": {"message": f"Hermes-managed LLM route failed: {type(exc).__name__}"}},
                    )
                    return
                self._send_json(HTTPStatus.OK, response)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="brainstack-hermes-llm-proxy", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _resolve_client(self, requested_model: str) -> tuple[Any, str]:
        if self.client_resolver is not None:
            client, model = self.client_resolver(self.provider, requested_model)
            if client is None:
                raise RuntimeError("Hermes-managed test resolver returned no client")
            return client, _text(model or requested_model or self.model)
        try:
            from agent.auxiliary_client import resolve_provider_client
        except Exception as exc:
            raise RuntimeError("Hermes auxiliary router is not importable") from exc
        client, model = resolve_provider_client(self.provider, model=requested_model or self.model)
        if client is None:
            raise RuntimeError(f"Hermes provider route unavailable: {self.provider}")
        return client, _text(model or requested_model or self.model)

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_model = _text(payload.get("model") or self.model)
        client, model = self._resolve_client(requested_model)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": payload.get("messages") or [],
            "timeout": float(payload.get("timeout") or self.timeout_seconds),
        }
        for key in ("temperature", "response_format", "tools", "tool_choice"):
            if key in payload:
                kwargs[key] = payload[key]
        if "max_completion_tokens" in payload:
            kwargs["max_completion_tokens"] = payload["max_completion_tokens"]
        elif "max_tokens" in payload:
            kwargs["max_tokens"] = payload["max_tokens"]
        response = client.chat.completions.create(**kwargs)
        content = _response_content(response)
        usage = _usage_dict(getattr(response, "usage", None) or (response.get("usage") if isinstance(response, dict) else None))
        return {
            "id": f"brainstack-hermes-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }


__all__ = ["HermesManagedLLMProxy"]
