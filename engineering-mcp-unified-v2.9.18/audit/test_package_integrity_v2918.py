"""Packaging and deployment tests without running Windows/WSL installation."""
from pathlib import Path
import ast
import base64
import codecs
import gzip
import hashlib
import importlib.util
import re
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'audit/engineering_mcp_unified-v2.9.18.py'
PS=ROOT/'install-engineering-mcp-unified-v2.9.18.ps1'
VERIFY=ROOT/'verify-engineering-mcp-unified-v2.9.18.ps1'


def text(path): return path.read_text(encoding='utf-8-sig')
def value(source,name): return re.search(r'\$'+name+r' = "([0-9a-f]{64})"',source)[1]


def test_embedded_payload_equals_complete_audit_source():
    src=text(PS)
    payload=re.search(r"\$EmbeddedBootstrapGzipBase64\s*=\s*@'\n(.*?)\n'@",src,re.S)[1]
    raw=gzip.decompress(base64.b64decode(payload))
    assert raw==SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==value(src,'EmbeddedBootstrapSha256')


def test_verifier_pinned_hashes_and_no_absent_repair_dependency():
    v=text(VERIFY)
    assert value(v,'ExpectedInstallerSha256')==hashlib.sha256(PS.read_bytes()).hexdigest()
    assert value(v,'ExpectedBootstrapSha256')==hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert '$Repair' not in v and '$ExpectedRepairSha256' not in v
    assert 'samostatného router hotfixu' not in v


@pytest.mark.parametrize('p',[PS,VERIFY])
def test_powershell_utf8_bom_crlf(p):
    raw=p.read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    assert b'\n' not in raw.replace(b'\r\n',b'')


def test_no_patch_no_cache_no_old_installer_in_distribution():
    for p in ROOT.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts:
            assert p.suffix not in ('.patch','.diff','.pyc')
    assert list(ROOT.glob('install-*.ps1'))==[PS]


def test_stale_wrapper_list_never_removes_current_release():
    data=text(PS)
    start=data.index('foreach ($staleName in @(')
    block=data[start:data.index('    )) {',start)]
    assert 'install-engineering-mcp-unified-v2.9.11.ps1' in block
    assert PS.name not in block


def test_ps_required_source_markers():
    ps=text(PS); src=text(SOURCE)
    section=ps[ps.index('$requiredMarkers = [ordered]@{'):]
    section=section[:section.index('\n    }')]
    keys=re.findall(r"^\s*'((?:[^']|'')*)'\s*=",section,re.M)
    assert len(keys)>=118
    missing=[k.replace("''", "'") for k in keys if k.replace("''", "'") not in src]
    assert not missing,missing


def test_verifier_required_source_markers():
    v=text(VERIFY);src=text(SOURCE)
    section=v[v.index('$RequiredMarkers = @('):]
    section=section[:section.index('\n)')]
    keys=re.findall(r"^\s*'((?:[^']|'')*)'[,]?\s*$",section,re.M)
    assert len(keys)>=62
    assert all(k.replace("''", "'") in src for k in keys)


def test_verifier_embedded_python_dynamic_checks():
    v=text(VERIFY)
    code=re.search(r"\$code = @'\n(.*?)\n'@",v,re.S)[1]
    cp=subprocess.run([sys.executable,'-W','error','-c',code,str(SOURCE),value(v,'ExpectedComponentSha256')],
                      capture_output=True,text=True,timeout=30)
    assert cp.returncode==0,cp.stdout+'\n'+cp.stderr


def test_embedded_component_and_nat_register_equal_audit_files():
    spec=importlib.util.spec_from_file_location('pack2912',SOURCE)
    main=importlib.util.module_from_spec(spec);spec.loader.exec_module(main)
    import zlib
    raw=zlib.decompress(base64.b85decode(main.PHYSNEMO_COMPONENT_B85))
    assert hashlib.sha256(raw).hexdigest()==main.PHYSNEMO_COMPONENT_SOURCE_SHA256
    assert raw==(ROOT/'audit/engineering_mcp_physnemo_component-v1.2.10.py').read_bytes()
    component=main.physnemo_component()
    assert component.PLUGIN_REGISTER==(ROOT/'audit/engineering_physnemo_nat-register-v1.2.10.py').read_text()


def test_deploy_self_writes_current_complete_source_and_preserves_user_data(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('deploy2912',SOURCE)
    main=importlib.util.module_from_spec(spec);spec.loader.exec_module(main)
    target=tmp_path/SOURCE.name
    (tmp_path/'artifacts').mkdir()
    artifact=tmp_path/'artifacts/keep.txt';artifact.write_text('user-data')
    config=tmp_path/'config.json';config.write_text('{"existing":true}')
    old=tmp_path/'engineering_mcp_unified-v2.9.11.py';old.write_text('old backup')
    monkeypatch.setattr(main,'APP_HOME',tmp_path)
    monkeypatch.setattr(main,'INSTALLED_SCRIPT',target)
    monkeypatch.setattr(main,'ensure_dirs',lambda:None)
    main.deploy_self()
    assert target.read_bytes()==SOURCE.read_bytes()
    assert artifact.read_text()=='user-data' and config.read_text()=='{"existing":true}'
    assert old.read_text()=='old backup'


def test_all_shipped_python_syntax_including_python312_grammar():
    for path in ROOT.rglob('*.py'):
        src=path.read_text(encoding='utf-8-sig')
        compile(src,str(path),'exec')
        ast.parse(src,filename=str(path),feature_version=(3,12))
