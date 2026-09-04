"""Unit tests for ``OpenAICompatProvider`` request mapping — monkeypatched
OpenAI client, no network, no MT5.

Verifies: cfg -> ``chat.completions.create`` params (model / messages /
max_tokens / response_format), the ``response_format`` gating behind
``llm_structured_mode``, ``content=None`` -> ``LLMTruncatedError``, and that the
client is constructed once with base_url/timeout/max_retries from cfg.
"""

from __future__ import annotations

import pytest
from _llm_fixtures import llm_cfg, make_evidence

from ai_trading.llm import provider as provider_module
from ai_trading.llm.prompt import build_prompt
from ai_trading.llm.provider import LLMTruncatedError, OpenAICompatProvider
from ai_trading.llm.schema import narrative_response_format


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        self._client.created_kwargs = kwargs
        return _FakeResp(self._client.content)


class _FakeChat:
    def __init__(self, client):
        self.completions = _FakeCompletions(client)


class _FakeClient:
    def __init__(self, content="{}"):
        self.content = content
        self.created_kwargs = None
        self.chat = _FakeChat(self)


@pytest.mark.unit
def test_client_constructed_once_with_cfg_overrides(monkeypatch):
    cfg = llm_cfg()
    construction = {}
    fake = _FakeClient()

    def factory(*args, **kwargs):
        construction.update(kwargs)
        return fake

    monkeypatch.setattr(provider_module, "OpenAI", factory)
    OpenAICompatProvider(cfg)
    assert construction["api_key"] == cfg.llm_api_key
    assert construction["base_url"] == cfg.llm_base_url
    assert construction["timeout"] == cfg.llm_timeout_ms / 1000
    assert construction["max_retries"] == cfg.llm_max_retries


@pytest.mark.unit
def test_request_params_mapped(monkeypatch):
    cfg = llm_cfg()
    fake = _FakeClient()
    monkeypatch.setattr(provider_module, "OpenAI", lambda *a, **k: fake)
    provider = OpenAICompatProvider(cfg)

    evidence = make_evidence()
    system, user = build_prompt(evidence)
    resp_fmt = narrative_response_format()

    result = provider.build_narrative(evidence, resp_fmt, cfg=cfg)
    assert isinstance(result, str)

    kwargs = fake.created_kwargs
    assert kwargs["model"] == cfg.llm_model
    assert kwargs["max_tokens"] == cfg.llm_max_tokens
    assert kwargs["messages"] == [*system, *user]
    assert kwargs["response_format"] == resp_fmt


@pytest.mark.unit
def test_content_none_raises_llm_truncated_error(monkeypatch):
    cfg = llm_cfg()
    fake = _FakeClient(content=None)
    monkeypatch.setattr(provider_module, "OpenAI", lambda *a, **k: fake)
    provider = OpenAICompatProvider(cfg)

    with pytest.raises(LLMTruncatedError):
        provider.build_narrative(make_evidence(), narrative_response_format(), cfg=cfg)


@pytest.mark.unit
def test_response_format_gated_by_structured_mode(monkeypatch):
    # json_object mode -> {"type": "json_object"}
    cfg = llm_cfg(llm_structured_mode="json_object")
    fake = _FakeClient('{"verdict":"confirm"}')
    monkeypatch.setattr(provider_module, "OpenAI", lambda *a, **k: fake)
    provider = OpenAICompatProvider(cfg)
    provider.build_narrative(make_evidence(), narrative_response_format(), cfg=cfg)
    assert fake.created_kwargs["response_format"] == {"type": "json_object"}

    # none mode -> response_format omitted entirely
    cfg2 = llm_cfg(llm_structured_mode="none")
    fake2 = _FakeClient('{"verdict":"confirm"}')
    monkeypatch.setattr(provider_module, "OpenAI", lambda *a, **k: fake2)
    provider2 = OpenAICompatProvider(cfg2)
    provider2.build_narrative(make_evidence(), narrative_response_format(), cfg=cfg2)
    assert "response_format" not in fake2.created_kwargs
