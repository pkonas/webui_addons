"""Offline protocol tests; no real model, credentials, NAT, or WSL is used."""
from __future__ import annotations

import asyncio
import codecs
import copy
import importlib.util
import json
from pathlib import Path
import textwrap

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "engineering_mcp_unified-v2.9.18.py").read_text()
START = SOURCE.index("                # ENGINEERING_MCP_PHYSNEMO_SSE_COMPAT_V1")
END = SOURCE.index('                @self.get(', START)
AFTER = SOURCE[START:END]
GOOD = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1789928078,
    "model": "configured-model",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Příliš žluťoučký kůň.\nOK"},
                 "finish_reason": "stop", "logprobs": None}],
    "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
}


def events(response):
    # The SDK consumes SSE data fields, not arbitrary JSON bodies.
    return [json.loads(block[6:]) for block in response.text.split("\n\n")
            if block.startswith("data: ") and block != "data: [DONE]"]


def make_app(source=AFTER, completion=None, *, raw=None, status=200, media="application/json", fail=False):
    app = FastAPI()
    calls = []
    data = copy.deepcopy(GOOD if completion is None else completion)
    content = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8")

    def config(request):
        if request.headers.get("authorization") != "Bearer TEST-ONLY":
            raise HTTPException(status_code=403, detail="Invalid bridge credential")
        return "http://upstream.test", "PRIVATE-UPSTREAM-TEST-KEY", "configured-model", "TEST-ONLY"

    def upstream(method, target, key, **kwargs):
        calls.append((method, target, key, kwargs))
        if fail:
            raise TimeoutError("private diagnostic must not leak")
        return status, content, media, {"Content-Type": media, "Content-Length": str(len(content)),
                                       "x-request-id": "test-request"}

    env = {
        "asyncio": asyncio, "json": json, "HTTPException": HTTPException, "BOOTSTRAPPER_VERSION": "2.9.18",
        "JSONResponse": JSONResponse, "Response": Response, "_EngineeringMCPRequest": Request,
        "_physnemo_agent_bridge_config": config, "_physnemo_openwebui_request": upstream,
    }
    exec(compile("def install(self):\n" + textwrap.indent(textwrap.dedent(source), "    "), "route-fixture", "exec"), env)
    env["install"](app)
    return app, calls


def post(app, payload=None, **kwargs):
    with TestClient(app) as client:
        return client.post("/openwebui-api/chat/completions",
                           headers={"Authorization": "Bearer TEST-ONLY"},
                           json=payload if payload is not None else {"model": "configured-model", "stream": True},
                           **kwargs)


@pytest.mark.parametrize("stream", [False, True, None])
def test_protocol_and_upstream_options(stream):
    app, calls = make_app()
    response = post(app, {"model": "configured-model", "stream": stream,
                          "stream_options": {"include_usage": True}})
    assert response.status_code == 200
    assert response.headers["x-engineering-mcp-bridge-hotfix"] == "sse-compat-1"
    assert response.headers["x-request-id"] == "test-request"
    assert len(calls) == 1
    assert calls[0][0:3] == ("POST", "http://upstream.test/api/chat/completions", "PRIVATE-UPSTREAM-TEST-KEY")
    upstream = json.loads(calls[0][3]["body"])
    assert upstream["stream"] is False
    assert "stream_options" not in upstream
    assert calls[0][3]["accept"] == "application/json"
    if stream:
        assert response.headers["content-type"].startswith("text/event-stream")
        frames = events(response)
        assert len(frames) == 3
        assert frames[0]["choices"][0]["delta"]["content"] == GOOD["choices"][0]["message"]["content"]
        assert frames[1]["choices"][0]["finish_reason"] == "stop"
        assert frames[2]["choices"] == []
        assert frames[2]["usage"] == GOOD["usage"]
        assert response.text.endswith("data: [DONE]\n\n")
    else:
        assert response.headers["content-type"] == "application/json"
        assert response.json() == GOOD
    assert int(response.headers["content-length"]) == len(response.content)


def test_stream_without_usage():
    response = post(make_app()[0])
    assert len(events(response)) == 2
    assert all("usage" not in event for event in events(response))


def test_absent_stream_defaults_to_json_and_model_is_injected():
    app, calls = make_app()
    response = post(app, {"messages": [{"role": "user", "content": "test"}]})
    assert response.headers["content-type"] == "application/json"
    assert json.loads(calls[0][3]["body"])["model"] == "configured-model"


def test_request_parameters_preserved():
    app, calls = make_app()
    payload = {"stream": True, "messages": [{"role": "user", "content": "test"}],
               "max_tokens": 100, "tools": [{"type": "function", "function": {"name": "test"}}],
               "tool_choice": "auto", "stop": ["STOP"], "temperature": 0.1}
    post(app, payload)
    body = json.loads(calls[0][3]["body"])
    for key in payload.keys() - {"stream"}:
        assert body[key] == payload[key]


def test_tool_calls_with_null_content():
    data = copy.deepcopy(GOOD)
    tools = [{"id": "call-0", "type": "function", "function": {"name": "solve", "arguments": '{"x":1}'}},
             {"id": "call-1", "type": "function", "function": {"name": "inspect", "arguments": "{}"}}]
    data["choices"][0].update(message={"role": "assistant", "content": None, "tool_calls": tools},
                               finish_reason="tool_calls")
    response = post(make_app(completion=data)[0])
    assert response.status_code == 200
    chunks = events(response)
    assert chunks[0]["choices"][0]["delta"]["content"] is None
    actual = chunks[0]["choices"][0]["delta"]["tool_calls"]
    assert actual == [{**tool, "index": n} for n, tool in enumerate(tools)]
    assert chunks[1]["choices"][0]["finish_reason"] == "tool_calls"


def test_legacy_function_call():
    data = copy.deepcopy(GOOD)
    data["choices"][0]["message"] = {"role": "assistant", "content": None,
                                       "function_call": {"name": "solve", "arguments": "{}"}}
    data["choices"][0]["finish_reason"] = "function_call"
    response = post(make_app(completion=data)[0])
    assert response.status_code == 200
    assert events(response)[0]["choices"][0]["delta"]["function_call"]["name"] == "solve"


def test_refusal_is_preserved_not_retried():
    data = copy.deepcopy(GOOD)
    data["choices"][0]["message"] = {"role": "assistant", "content": None, "refusal": "No."}
    app, calls = make_app(completion=data)
    response = post(app)
    assert response.status_code == 200
    assert events(response)[0]["choices"][0]["delta"]["refusal"] == "No."
    assert len(calls) == 1


def test_multiple_choices_finish_reasons_and_metadata():
    data = copy.deepcopy(GOOD)
    data["system_fingerprint"] = "fp-test"
    data["service_tier"] = "default"
    data["choices"].append({"index": 1, "message": {"role": "assistant", "content": "partial"}, "finish_reason": "length"})
    response = post(make_app(completion=data)[0])
    chunks = events(response)
    assert len(chunks[0]["choices"]) == 2
    assert [c["finish_reason"] for c in chunks[1]["choices"]] == ["stop", "length"]
    assert all(c["system_fingerprint"] == "fp-test" and c["id"] == data["id"] for c in chunks)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_upstream_errors_are_not_fake_streams(status):
    raw = b'{"error":{"message":"upstream failed"}}'
    app, calls = make_app(raw=raw, status=status)
    response = post(app)
    assert response.status_code == status and response.content == raw
    assert response.headers["content-type"] == "application/json"
    assert len(calls) == 1


@pytest.mark.parametrize("raw,code", [
    (b"", "openwebui_invalid_json"),
    (b"<html>not a completion</html>", "openwebui_invalid_json"),
    (b"data: [DONE]\n\n", "openwebui_invalid_json"),
    (b"[]", "openwebui_invalid_completion"),
    (b"null", "openwebui_invalid_completion"),
    (b'{"error":{"message":"PRIVATE-BODY"}}', "openwebui_upstream_error"),
    (b'{"choices":[]}', "openwebui_no_choices"),
    (b'{"choices":[{}]}', "openwebui_invalid_choice"),
])
def test_invalid_upstream_body_is_explicit_error(raw, code):
    response = post(make_app(raw=raw)[0])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == code
    assert "PRIVATE-BODY" not in response.text


@pytest.mark.parametrize("field,value,code", [
    ("content", "", "openwebui_no_usable_message"),
    ("content", "   \n", "openwebui_no_usable_message"),
    ("content", None, "openwebui_no_usable_message"),
    ("content", {"unexpected": 1}, "openwebui_invalid_choice"),
    ("role", "user", "openwebui_invalid_choice"),
    ("tool_calls", {}, "openwebui_invalid_tool_calls"),
    ("tool_calls", ["bad"], "openwebui_invalid_tool_calls"),
    ("function_call", {}, "openwebui_invalid_tool_calls"),
])
def test_invalid_message(field, value, code):
    data = copy.deepcopy(GOOD)
    data["choices"][0]["message"][field] = value
    response = post(make_app(completion=data)[0])
    assert response.status_code == 502 and response.json()["error"]["code"] == code


def test_reasoning_only_is_not_promoted_to_answer():
    data = copy.deepcopy(GOOD)
    data["choices"][0]["message"] = {"role": "assistant", "content": None, "reasoning_content": "PRIVATE-THOUGHT"}
    data["choices"][0]["finish_reason"] = "length"
    response = post(make_app(completion=data)[0])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openwebui_no_usable_message"
    assert "PRIVATE-THOUGHT" not in response.text


def test_missing_finish_reason_is_error():
    data = copy.deepcopy(GOOD)
    data["choices"][0]["finish_reason"] = None
    assert post(make_app(completion=data)[0]).status_code == 502


def test_duplicate_choice_indices_are_error():
    data = copy.deepcopy(GOOD)
    data["choices"].append(copy.deepcopy(data["choices"][0]))
    assert post(make_app(completion=data)[0]).status_code == 502


def test_generated_stream_metadata_when_missing():
    data = copy.deepcopy(GOOD)
    for key in ("id", "created", "model"):
        data.pop(key)
    chunks = events(post(make_app(completion=data)[0]))
    assert chunks[0]["id"].startswith("chatcmpl-physnemo-")
    assert type(chunks[0]["created"]) is int
    assert chunks[0]["model"] == "configured-model"


@pytest.mark.parametrize("stream", ["false", "true", 1, 0, {}, []])
def test_bad_stream_types(stream):
    app, calls = make_app()
    assert post(app, {"stream": stream}).status_code == 400
    assert calls == []


def test_bad_stream_options_type():
    app, calls = make_app()
    assert post(app, {"stream": True, "stream_options": []}).status_code == 400
    assert calls == []


def test_model_guard_retained():
    app, calls = make_app()
    assert post(app, {"model": "not-allowed", "stream": True}).status_code == 400
    assert calls == []


def test_auth_guard_retained():
    app, calls = make_app()
    with TestClient(app) as client:
        assert client.post("/openwebui-api/chat/completions", json={"stream": True}).status_code == 403
    assert calls == []


def test_body_limit_retained():
    app, calls = make_app()
    with TestClient(app) as client:
        response = client.post("/openwebui-api/chat/completions", headers={"Authorization": "Bearer TEST-ONLY"},
                               content=b"x" * (8 * 1024 * 1024 + 1))
    assert response.status_code == 413 and calls == []


def test_transport_failure_is_clear_and_redacted():
    app, calls = make_app(fail=True)
    response = post(app)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openwebui_bridge_unreachable"
    assert "private diagnostic" not in response.text
    assert len(calls) == 1


def test_unexpected_204_status():
    response = post(make_app(status=204, raw=b"")[0])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openwebui_unexpected_status"


def test_utf8_bom_and_json_type_normalization():
    raw = codecs.BOM_UTF8 + json.dumps(GOOD).encode()
    response = post(make_app(raw=raw, media="text/plain")[0])
    assert response.status_code == 200 and len(events(response)) == 2


