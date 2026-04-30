from __future__ import annotations

from types import SimpleNamespace
import urllib.request
import json

from brainstack.hindsight_hermes_llm_proxy import HermesManagedLLMProxy


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["model"] == "gpt-5.5"
        assert kwargs["messages"][0]["content"] == "return json"
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok": true}'),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
        )


class FakeClient:
    chat = SimpleNamespace(completions=FakeCompletions())


def test_hermes_managed_llm_proxy_exposes_openai_wire_chat_endpoint() -> None:
    proxy = HermesManagedLLMProxy(
        model="gpt-5.5",
        client_resolver=lambda provider, model: (FakeClient(), model),
    ).start()
    try:
        body = json.dumps(
            {
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": "return json"}],
                "max_completion_tokens": 32,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            proxy.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        proxy.close()

    assert payload["model"] == "gpt-5.5"
    assert payload["choices"][0]["message"]["content"] == '{"ok": true}'
    assert payload["usage"] == {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
