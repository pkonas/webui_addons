#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "engineering_mcp_physnemo_component-v1.2.10.py"

spec = importlib.util.spec_from_file_location("physnemo_component_v123", SOURCE)
assert spec and spec.loader
component = importlib.util.module_from_spec(spec)
spec.loader.exec_module(component)


def local_wsl_run(_distro, script, *, check=False, timeout=None, stage=None, **_kwargs):
    result = subprocess.run(
        ["bash", "--noprofile", "--norc"],
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"local stage {stage!r} failed with {result.returncode}:\n{result.stdout}{result.stderr}"
        )
    return result


def create_signature(root: Path) -> None:
    (root / "plugin").mkdir(parents=True)
    (root / "plugin" / "pyproject.toml").write_text(
        '[project]\nname = "engineering-physnemo-nat"\n', encoding="utf-8"
    )


def test_existing_artifact_store_is_adopted_and_preserved() -> None:
    with tempfile.TemporaryDirectory(prefix="physnemo-artifact-root-") as td:
        root = Path(td) / "engineering-mcp-physnemo"
        root.mkdir()
        create_signature(root)
        artifact = root / "artifacts" / "job-test" / "artifacts" / "result.csv"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("x,y\n1,2\n", encoding="utf-8")
        # Reproduce the user's state: a marker exists but cannot be trusted, so
        # the partial-adoption allowlist must decide whether the root is safe.
        (root / ".engineering-mcp-physnemo-managed").write_text(
            "interrupted-marker\n", encoding="utf-8"
        )
        original = component.wsl_run
        component.wsl_run = local_wsl_run
        try:
            result = component.assert_managed_wsl_root(
                "local", str(root), allow_partial_adoption=True
            )
            assert result["status"] == "adopted", result
            assert "artifacts" in result["entries"], result
            assert artifact.read_text(encoding="utf-8") == "x,y\n1,2\n"
            marker = (root / ".engineering-mcp-physnemo-managed").read_text(encoding="utf-8")
            assert "managed_by=engineering-mcp-physnemo" in marker
            assert "version=1.2.10" in marker
            second = component.assert_managed_wsl_root(
                "local", str(root), allow_partial_adoption=False
            )
            assert second["status"] == "managed", second
            assert artifact.exists()
        finally:
            component.wsl_run = original


def expect_refusal(kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"physnemo-refuse-{kind}-") as td:
        root = Path(td) / "engineering-mcp-physnemo"
        root.mkdir()
        create_signature(root)
        if kind == "file":
            (root / "artifacts").write_text("not a directory", encoding="utf-8")
        elif kind == "symlink":
            target = Path(td) / "outside"
            target.mkdir()
            (root / "artifacts").symlink_to(target, target_is_directory=True)
        elif kind == "unknown":
            (root / "user-data.txt").write_text("preserve me", encoding="utf-8")
        else:
            raise AssertionError(kind)
        original = component.wsl_run
        component.wsl_run = local_wsl_run
        try:
            try:
                component.assert_managed_wsl_root(
                    "local", str(root), allow_partial_adoption=True
                )
            except RuntimeError as exc:
                message = str(exc)
                assert "Refusing non-empty unmanaged install directory" in message
            else:
                raise AssertionError(f"unsafe {kind} was accepted")
        finally:
            component.wsl_run = original


def main() -> None:
    assert component.WSL_MANAGED_ROOT_MARKER == "ENGINEERING_MCP_PHYSNEMO_ROOT_V4_ARTIFACTS_ALLOWED"
    assert component.MANAGED_ROOT_ARTIFACTS_CONTRACT == "MANAGED_ROOT_ARTIFACTS_DIRECTORY_V1"
    assert "artifacts" in component.MANAGED_ROOT_DIRECTORIES
    test_existing_artifact_store_is_adopted_and_preserved()
    for kind in ("file", "symlink", "unknown"):
        expect_refusal(kind)
    print("MANAGED_ARTIFACT_ROOT_V2912_TESTS_OK")


if __name__ == "__main__":
    main()
