#!/usr/bin/env python3
"""Regression test for NAT 1.9 component dependency ordering.

The 1.2.3 plugin used ``agent_name: str``. NAT therefore could not add an edge
from ``physnemo__solve`` to ``physnemo_agent`` and was free to build the solve
function first. 1.2.10 uses ``FunctionRef | None`` so NAT's dependency graph can
order the referenced agent before the wrapper function.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_core import core_schema

ROOT = Path(__file__).resolve().parent
COMPONENT = ROOT / "engineering_mcp_physnemo_component-v1.2.10.py"


def load_component():
    spec = importlib.util.spec_from_file_location("physnemo_component_124", COMPONENT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubFunctionRef(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler, **_kwargs):
        return core_schema.no_info_plain_validator_function(cls)


class StubFunctionBaseConfig(BaseModel):
    def __init_subclass__(cls, name=None, **kwargs):  # NAT's typed config accepts name=...
        super().__init_subclass__(**kwargs)
        cls._component_type_name = name


class StubBuilder:
    async def get_function(self, name):
        return name


class StubFunctionInfo:
    @classmethod
    def from_fn(cls, fn, **kwargs):
        return (fn, kwargs)


def stub_register_function(*, config_type):
    def decorate(fn):
        fn._nat_config_type = config_type
        return fn
    return decorate


def execute_plugin_source(source: str):
    modules = {
        "nat": types.ModuleType("nat"),
        "nat.builder": types.ModuleType("nat.builder"),
        "nat.builder.builder": types.ModuleType("nat.builder.builder"),
        "nat.builder.function_info": types.ModuleType("nat.builder.function_info"),
        "nat.cli": types.ModuleType("nat.cli"),
        "nat.cli.register_workflow": types.ModuleType("nat.cli.register_workflow"),
        "nat.data_models": types.ModuleType("nat.data_models"),
        "nat.data_models.component_ref": types.ModuleType("nat.data_models.component_ref"),
        "nat.data_models.function": types.ModuleType("nat.data_models.function"),
    }
    modules["nat.builder.builder"].Builder = StubBuilder
    modules["nat.builder.function_info"].FunctionInfo = StubFunctionInfo
    modules["nat.cli.register_workflow"].register_function = stub_register_function
    modules["nat.data_models.component_ref"].FunctionRef = StubFunctionRef
    modules["nat.data_models.component_ref"].LLMRef = StubFunctionRef
    modules["nat.data_models.function"].FunctionBaseConfig = StubFunctionBaseConfig

    previous = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    namespace = {"__name__": "engineering_physnemo_nat.register", "__file__": "<embedded-plugin>"}
    try:
        exec(compile(source, "<embedded-plugin>", "exec"), namespace)
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return namespace


def main() -> None:
    component = load_component()
    assert component.BOOTSTRAPPER_VERSION == "1.2.10"
    assert component.NAT_DEPENDENCY_CONTRACT == "NAT_1_9_FUNCTION_REF_DEPENDENCY_V1"
    assert "from nat.data_models.component_ref import FunctionRef" in component.PLUGIN_REGISTER
    assert "agent_name: FunctionRef | None = None" in component.PLUGIN_REGISTER
    assert "agent_name: str" not in component.PLUGIN_REGISTER

    configured = yaml.safe_load(component.render_nat_config(
        "/managed/source", "v2.2.2", "/managed/artifacts",
        "http://127.0.0.1:8200/physnemo/artifacts", "s" * 64,
        agent_configured=True,
    ))
    unconfigured = yaml.safe_load(component.render_nat_config(
        "/managed/source", "v2.2.2", "/managed/artifacts",
        "http://127.0.0.1:8200/physnemo/artifacts", "s" * 64,
        agent_configured=False,
    ))
    assert configured["functions"]["physnemo__solve"]["agent_name"] == "physnemo_agent"
    assert unconfigured["functions"]["physnemo__solve"]["agent_name"] is None
    assert "physnemo_agent" not in unconfigured["functions"]

    namespace = execute_plugin_source(component.PLUGIN_REGISTER)
    config_type = namespace["PhysNeMoSolveConfig"]
    config_type.model_rebuild(_types_namespace=namespace)
    cfg = config_type(
        agent_name="physnemo_agent",
        agent_configured=True,
        source_root="/managed/source",
        source_ref="v2.2.2",
        artifact_root="/managed/artifacts",
        artifact_base_url="http://127.0.0.1:8200/physnemo/artifacts",
        artifact_secret="s" * 64,
    )
    assert isinstance(cfg.agent_name, StubFunctionRef)
    discovered = [str(getattr(cfg, field)) for field in type(cfg).model_fields if isinstance(getattr(cfg, field), StubFunctionRef)]
    assert discovered == ["physnemo_agent"]

    # Intentionally place solve first. A reference-aware topological walk must
    # still place its referenced function first.
    functions = {"physnemo__solve": cfg, "physnemo_agent": object()}
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise AssertionError("unexpected dependency cycle")
        visiting.add(name)
        value = functions[name]
        for field in getattr(type(value), "model_fields", {}):
            dependency = getattr(value, field)
            if isinstance(dependency, StubFunctionRef):
                visit(str(dependency))
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for name in functions:
        visit(name)
    assert order.index("physnemo_agent") < order.index("physnemo__solve"), order
    print("PHYSNEMO_FUNCTIONREF_DEPENDENCY_V1_OK")


if __name__ == "__main__":
    main()
