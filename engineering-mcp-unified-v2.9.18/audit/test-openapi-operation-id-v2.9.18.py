#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "engineering_mcp_unified-v2.9.18.py"


def load_module():
    home = tempfile.mkdtemp(prefix="emcp-v2911-openapi-")
    os.environ["ENGINEERING_MCP_HOME"] = home
    spec = importlib.util.spec_from_file_location("emcp_v2911", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema(module):
    operations = [
        "physnemo__environment_info",
        "physnemo__solve",
        "physnemo__job_status",
        "physnemo__list_artifacts",
        "physnemo__get_artifact",
    ]
    paths = {
        f"/{name}": {"post": {"operationId": f"tool_{name}_post", "responses": {"200": {"description": "ok"}}}}
        for name in operations
    }
    for name in ("physnemo__solve", "physnemo__job_status"):
        paths[f"/{name}"]["post"]["requestBody"] = {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"client_request_id": {"type": "string"}}
        }}}}
    # The gateway-native gallery deliberately has a readable URL path and a
    # stable tool operation id. Open WebUI consumes operationId.
    paths["/render-artifacts"] = {
        "post": {
            "operationId": "physnemo__render_artifacts",
            "responses": {"200": {"description": "ok"}},
        }
    }
    paths[f"/{module.documentation_path('physnemo')}"] = {"get": {"operationId": "docs"}}
    return {
        "openapi": "3.1.0",
        "info": {"title": module.integration_title("physnemo"), "version": "1"},
        "paths": paths,
    }


def test_inventory_prefers_operation_id(module):
    data = schema(module)
    tool_paths, path_names, operation_ids, mapping = module._openapi_tool_inventory(
        data["paths"],
        excluded_paths=(f"/{module.documentation_path('physnemo')}",),
    )
    assert "/render-artifacts" in tool_paths
    assert "render-artifacts" in path_names
    assert "physnemo__render_artifacts" in operation_ids
    assert mapping["/render-artifacts"] == ["physnemo__render_artifacts"]
    assert not module.missing_required_tool_groups("physnemo", path_names | operation_ids)


def test_inventory_path_fallback(module):
    paths = {"/legacy_tool": {"post": {"responses": {"200": {"description": "ok"}}}}}
    tool_paths, path_names, operation_ids, mapping = module._openapi_tool_inventory(paths)
    assert tool_paths == ["/legacy_tool"]
    assert path_names == {"legacy_tool"}
    assert operation_ids == set()
    assert mapping == {"/legacy_tool": []}


def test_canonical_fastapi_operation_ids(module):
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(generate_unique_id_function=module._engineering_openapi_operation_id)

    async def tool():
        return {}

    app.post("/physnemo__solve")(tool)

    @app.post(
        "/render-artifacts",
        operation_id="physnemo__render_artifacts",
        response_class=HTMLResponse,
    )
    async def render(job_id: str = Body(..., embed=True)):
        return ""

    generated = app.openapi()["paths"]
    assert generated["/physnemo__solve"]["post"]["operationId"] == "physnemo__solve"
    assert generated["/render-artifacts"]["post"]["operationId"] == "physnemo__render_artifacts"


def test_check_endpoints_accepts_gateway_gallery(module):
    data = schema(module)
    module.configured_routes = lambda: ["physnemo"]
    module.tcp_open = lambda host, port: True
    module.atomic_write_json = lambda *args, **kwargs: None
    module.probe_physnemo_mcp = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("direct probe must not run for a ready route")
    )

    def fake_http(url, api_key, timeout=0):
        if url.endswith(module.openapi_schema_path("physnemo")):
            return 200, data, ""
        if url.endswith(module.documentation_path("physnemo")):
            return 200, {}, ""
        raise AssertionError(url)

    module._http_json_with_retry = fake_http
    result = module.check_endpoints(
        {"mcpo_port": 8200, "api_key": "test", "routes": ["physnemo"]},
        quiet=True,
    )
    server = result["servers"]["physnemo"]
    assert result["ok"] is True, result
    assert server["ready"] is True, server
    assert server["required_tools_ok"] is True
    assert server["missing_required_tool_groups"] == {}
    assert "render-artifacts" in server["tool_names"]
    assert "physnemo__render_artifacts" in server["openapi_operation_ids"]
    assert "physnemo__render_artifacts" in server["available_tool_names"]
    assert server["tool_operation_ids_by_path"]["/render-artifacts"] == [
        "physnemo__render_artifacts"
    ]
    assert server["tool_name_source"] == "path-segment-union-openapi.operationId"


def main():
    module = load_module()
    assert module.PHYSNEMO_OPENAPI_OPERATION_ID_CONTRACT == "OPENAPI_PATH_AND_OPERATION_ID_UNION_V1"
    assert module.PHYSNEMO_OPENAPI_CANONICAL_ID_CONTRACT == "OPENAPI_CANONICAL_MCP_OPERATION_IDS_V1"
    test_inventory_prefers_operation_id(module)
    print("PASS: operationId complements MCPO path names for gateway-native tools")
    test_inventory_path_fallback(module)
    print("PASS: legacy schemas without operationId use a path fallback")
    test_canonical_fastapi_operation_ids(module)
    print("PASS: MCPO paths become canonical OpenAPI operationIds")
    test_check_endpoints_accepts_gateway_gallery(module)
    print("PASS: PhysicsNeMo OpenAPI verification accepts render_artifacts")
    print("OPENAPI_OPERATION_ID_V2912_TESTS_OK")


if __name__ == "__main__":
    main()
