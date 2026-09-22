# ENGINEERING-MCP-UNIFIED-VERIFIER; VERSION=2.9.18; OPENWEBUI-NATIVE-LIVE-SYNC+ARTIFACT-GALLERY
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $Root "install-engineering-mcp-unified-v2.9.18.ps1"
$ExpectedInstallerSha256 = "98cae5d489291cc0568766756ba08da360ba57dc486fe91f1fea013fe7a32586"
$ExpectedBootstrapSha256 = "827070d109bea940281ddf7af8e4830e0f1df6eb8539ca1c24207a28ba088bcb"
$ExpectedComponentSha256 = "0f39f381bf2fec3325e12c171d70e433fd2fb8b117e7d9e1657d08fd02a96ea6"

function Fail-Verification {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "FAIL: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    Fail-Verification "Chybí autoritativní instalátor: $Installer"
}
$installerHash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHash -ne $ExpectedInstallerSha256) {
    Fail-Verification "SHA-256 instalátoru nesouhlasí. Zjištěno: $installerHash"
}

$Tokens = $null
$ParseErrors = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $Installer, [ref]$Tokens, [ref]$ParseErrors
)
if ($ParseErrors.Count -gt 0) {
    $details = ($ParseErrors | ForEach-Object { $_.Message }) -join " | "
    Fail-Verification "PowerShell parser nalezl chyby: $details"
}

$ParameterNames = @($Ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
$RequiredParameters = @(
    "Install", "Resume", "Uninstall", "Community", "NoCommunity", "NoStart", "NoAutostart", "Force",
    "MatlabImageTest", "NoMatlabRepair", "ForceCloseMatlab", "MatlabHealthTimeout",
    "NoPhysNeMo", "PhysNeMoDistro", "PhysNeMoInstallDir", "PhysNeMoNatPort",
    "NeMoAgentToolkitVersion", "PhysicsNeMoVersion", "PhysicsNeMoProfile", "PhysicsNeMoSourceRef",
    "NoPhysNeMoPrerequisiteInstall", "PhysNeMoAgentBaseUrl", "PhysNeMoAgentModel",
    "PhysNeMoAgentApiKeyFile", "NoPhysNeMoAgentAutoDetect", "PhysNeMoOpenWebUIUrl",
    "PhysNeMoOpenWebUIApiKeyFile", "PhysNeMoArtifactBaseUrl",
    "OpenWebUIDatabase", "NoOpenWebUINativeSync", "NoOpenWebUIDlpRepair",
    "AllowPhysNeMoWithoutAgent",
    "NoWeKnora", "WeKnoraUrl", "WeKnoraApiUrl", "WeKnoraApiKeyFile", "WeKnoraTenantId",
    "WeKnoraTenantName", "WeKnoraCaCertificate", "WeKnoraDistro", "WeKnoraInstallDir",
    "NoWeKnoraAutoProvision", "WeKnoraAllowEmptyCatalog", "WeKnoraHealthTimeout", "Port", "StartupTimeout"
)
foreach ($name in $RequiredParameters) {
    if ($ParameterNames -notcontains $name) { Fail-Verification "Chybí parametr $name." }
}

$text = [System.IO.File]::ReadAllText($Installer)
$payloadMatch = [regex]::Match(
    $text,
    '(?s)\$EmbeddedBootstrapGzipBase64\s*=\s*@''\r?\n(?<payload>.*?)\r?\n''@'
)
if (-not $payloadMatch.Success) { Fail-Verification "Nelze nalézt vložený Python payload." }
try {
    $compressed = [Convert]::FromBase64String(($payloadMatch.Groups['payload'].Value -replace '\s', ''))
    $input = New-Object System.IO.MemoryStream(,$compressed)
    $gzip = New-Object System.IO.Compression.GZipStream($input, [IO.Compression.CompressionMode]::Decompress)
    $output = New-Object System.IO.MemoryStream
    $gzip.CopyTo($output)
    $gzip.Dispose(); $input.Dispose()
    $bootstrapBytes = $output.ToArray(); $output.Dispose()
} catch {
    Fail-Verification "Rozbalení vloženého Pythonu selhalo: $($_.Exception.Message)"
}
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $bootstrapHash = ([BitConverter]::ToString($sha.ComputeHash($bootstrapBytes))).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($bootstrapHash -ne $ExpectedBootstrapSha256) {
    Fail-Verification "SHA-256 vloženého Pythonu nesouhlasí. Zjištěno: $bootstrapHash"
}

$bootstrapText = [Text.Encoding]::UTF8.GetString($bootstrapBytes)
$RequiredMarkers = @(
    'def _physnemo_collect_upstream_sse('
    'def _physnemo_model_execution_verified('
    'physnemo_model_tools_verified'

    'PHYSNEMO_NATIVE_TOOL_DISPATCH_V5',
    'PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5',
    'chat_tool_registration_ready',
    'PHYSNEMO_OBSERVABLE_DELIVERY_V1',
    'PHYSNEMO_LIFECYCLE_SCHEMA_STALE',
    'PHYSNEMO_GALLERY_FAILED',
    'delivery_confirmed_by_browser',
    'PHYSNEMO_OPENWEBUI_CHAT_PROTOCOL = "OPENAI_BUFFERED_JSON_AND_SSE_V1"',
    'def _physnemo_bridge_chat_response(',
    'X-Engineering-MCP-Bridge-Protocol',
    'PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE',
    '--langchain --non-interactive',
    'BOOTSTRAPPER_VERSION = "2.9.18"',
    'PHYSNEMO_NAT_FUNCTION_CONTRACT = "NAT_1_9_GENERAL_AGENT_ARTIFACT_GALLERY_V2"',
    'PHYSNEMO_NAT_DEPENDENCY_CONTRACT = "NAT_1_9_FUNCTION_REF_DEPENDENCY_V1"',
    'PHYSNEMO_MANAGED_ROOT_PROTOCOL = "ENGINEERING_MCP_PHYSNEMO_ROOT_V4_ARTIFACTS_ALLOWED"',
    'PHYSNEMO_MANAGED_ARTIFACT_ROOT_CONTRACT = "MANAGED_ROOT_ARTIFACTS_DIRECTORY_V1"',
    'MANAGED_ROOT_DIRECTORIES',
    'PHYSNEMO_ARTIFACT_GALLERY_CONTRACT = "OPENWEBUI_INLINE_HTML_GALLERY_V1"',
    'PHYSNEMO_OPENWEBUI_AGENT_BRIDGE_CONTRACT = "WINDOWS_LOOPBACK_REVERSE_PROXY_V1"',
    'def probe_physnemo_agent_bridge',
    '/openwebui-api/chat/completions',
    'PHYSNEMO_GATEWAY_ROUTE',
    '_EngineeringMCPRequest',
    'PHYSNEMO_OPENWEBUI_SCHEMA_SYNC_CONTRACT = "OPENWEBUI_TOOL_SERVER_LIVE_REFRESH_V1"',
    'PHYSNEMO_OPENAPI_OPERATION_ID_CONTRACT = "OPENAPI_PATH_AND_OPERATION_ID_UNION_V1"',
    'PHYSNEMO_OPENAPI_CANONICAL_ID_CONTRACT = "OPENAPI_CANONICAL_MCP_OPERATION_IDS_V1"',
    'OPENWEBUI_NATIVE_DATABASE_SYNC_CONTRACT = "OPENWEBUI_NATIVE_SQLITE_LIVE_SYNC_V1"',
    'OPENWEBUI_MANAGED_API_KEY_CONTRACT = "OPENWEBUI_MANAGED_API_KEY_V1"',
    'OPENWEBUI_DLP_PREFLIGHT_CONTRACT = "OPENWEBUI_DLP_GLOBAL_FILTER_REPAIR_V1"',
    'OPENWEBUI_PHYSNEMO_READINESS_CONTRACT = "OPENWEBUI_PHYSNEMO_TOOL_EXECUTION_READINESS_V1"',
    'OPENWEBUI_ENGINEERING_TOOL_ROUTER_CONTRACT = "OPENWEBUI_GLOBAL_FILTER_TOOL_ID_INJECTION_V1"',
    'OPENWEBUI_ENGINEERING_TOOL_ROUTER_FILTER_CONTRACT = "ENGINEERING_MCP_TOOL_ROUTER_FILTER_V1"',
    'ENGINEERING_MCP_TOOL_ROUTER_PROBE_V1',
    'def _engineering_tool_router_self_test',
    'stdlib-self-test-shim',
    '_EngineeringRouterSelfTestBaseModel',
    'def _sync_openwebui_engineering_tool_router',
    '"server:physnemo"',
    'metadata_params["function_calling"] = "native"',
    '/api/v1/functions/create',
    'OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT',
    'def _discover_openwebui_sqlite',
    'def _ensure_openwebui_managed_api_key',
    'chat_tool_execution_ready',
    '/api/v1/configs/tool_servers',
    '/api/v1/configs/tool_servers/verify',
    '--openwebui-database',
    '--openwebui-native-sync',
    '--openwebui-dlp-repair',
    '--physnemo-allow-unconfigured-agent',
    'def _engineering_openapi_operation_id',
    'generate_unique_id_function',
    'def _openapi_tool_inventory',
    'tool_name_source": "path-segment-union-openapi.operationId"',
    'PHYSNEMO_OPENAPI_EXPECTED_TOOLS',
    'physnemo__render_artifacts',
    'def _physnemo_render_gallery',
    'auto_render_completed_physnemo_solve',
    'def sync_physnemo_openwebui_tool_server',
    '"Content-Disposition": "inline"',
    'PHYSNEMO_FORBIDDEN_MARKER_SCOPE_CONTRACT = "EMBEDDED_PLUGIN_ONLY_V1"',
    'PHYSNEMO_AGENT_OPTIONAL_INSTALL_CONTRACT = "NAT_AGENT_OPTIONAL_INSTALL_V1"',
    'physnemo__solve will return configuration_required until an LLM is configured',
    'present_forbidden = [marker for marker in forbidden if marker in plugin_register]',
    'from nat.data_models.component_ref import FunctionRef',
    'agent_name: FunctionRef | None = None',
    'agent = await builder.get_function(config.agent_name)',
    'max_turns: 32',
    'MAX_INLINE_IMAGE_BYTES = 12 * 1024 * 1024',
    '/artifacts/{job_id}/{filename}',
    '/input-files/{file_id}',
    'WEKNORA_ALLOWED_SCHEMES = frozenset({"http", "https"})',
    'MECHANICAL_STATIC_TOOLS_OPTION = "--static-tools"'
)
foreach ($marker in $RequiredMarkers) {
    if (-not $bootstrapText.Contains($marker)) { Fail-Verification "Vložený Python postrádá marker: $marker" }
}
if ($bootstrapText.Contains('physnemo__start_pinn_karman') -or $bootstrapText.Contains('physnemo__pinn_run_status')) {
    Fail-Verification "Vložený Python znovu obsahuje problémově specifický Kármánův solver."
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("engineering-mcp-verify-v2918-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$tempPython = Join-Path $tempRoot 'engineering_mcp_unified-v2.9.18.py'
[IO.File]::WriteAllBytes($tempPython, $bootstrapBytes)
$PythonChecked = $false
try {
    $commands = @()
    $Py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $Py) { $commands += ,@($Py.Source, '-3.12') }
    foreach ($name in @('python3.12', 'python.exe', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { $commands += ,@($command.Source) }
    }
    foreach ($entry in $commands) {
        $exe = $entry[0]
        $prefix = @()
        if ($entry.Count -gt 1) { $prefix = @($entry[1..($entry.Count - 1)]) }
        & $exe @prefix -W error -m py_compile $tempPython
        if ($LASTEXITCODE -ne 0) { continue }
        $code = @'
import base64, hashlib, importlib.util, json, sys, zlib
p=sys.argv[1]
expected=sys.argv[2]
s=importlib.util.spec_from_file_location("emcp_verify_v2918", p)
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
c=m.physnemo_component()
assert m.BOOTSTRAPPER_VERSION == "2.9.18"
assert m.PHYSNEMO_OPENWEBUI_AGENT_BRIDGE_CONTRACT == "WINDOWS_LOOPBACK_REVERSE_PROXY_V1"
assert callable(m.probe_physnemo_agent_bridge)
assert m.PHYSNEMO_OPENWEBUI_CHAT_PROTOCOL == "OPENAI_BUFFERED_JSON_AND_SSE_V1"
compile(m.PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE, "embedded-agent-bridge-check", "exec")
assert 'async def check_langchain(' in m.PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE
assert 'streaming=True' in m.PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE
assert c.BOOTSTRAPPER_VERSION == "1.2.10"
assert callable(m.probe_physnemo_native_tools)
assert callable(m._physnemo_model_execution_verified)
assert 'def _physnemo_collect_upstream_sse(' in __import__('pathlib').Path(p).read_text(encoding='utf-8')
assert 'JSON_ACTION_PROTOCOL = "PHYSNEMO_JSON_ACTION_V1"' in c.PLUGIN_REGISTER
assert 'async def _request_json_action(' in c.PLUGIN_REGISTER
assert 'async def _json_probe_model_step(' in c.PLUGIN_REGISTER
compile(m.PHYSNEMO_NATIVE_TOOLS_CHECK_SOURCE, "embedded-native-tool-check", "exec")
compile(c.PLUGIN_REGISTER, "embedded-nat-register", "exec")
assert 'PHYSNEMO_NATIVE_TOOL_DISPATCH_V5' in c.PLUGIN_REGISTER
assert 'PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5' in c.PLUGIN_REGISTER
assert 'async def _native_probe_model_step(' in c.PLUGIN_REGISTER
assert 'def _native_model_event(' in c.PLUGIN_REGISTER
assert 'tool_choice="required"' in c.PLUGIN_REGISTER
assert 'model-events.jsonl' in c.PLUGIN_REGISTER
assert c.NAT_FUNCTION_CONTRACT == "NAT_1_9_GENERAL_AGENT_ARTIFACT_GALLERY_V2"
assert c.NAT_DEPENDENCY_CONTRACT == "NAT_1_9_FUNCTION_REF_DEPENDENCY_V1"
assert c.WSL_MANAGED_ROOT_MARKER == "ENGINEERING_MCP_PHYSNEMO_ROOT_V4_ARTIFACTS_ALLOWED"
assert c.MANAGED_ROOT_ARTIFACTS_CONTRACT == "MANAGED_ROOT_ARTIFACTS_DIRECTORY_V1"
assert "artifacts" in tuple(c.MANAGED_ROOT_DIRECTORIES)
assert tuple(m.PHYSNEMO_OPENAPI_EXPECTED_TOOLS) == (
    "physnemo__environment_info", "physnemo__solve", "physnemo__job_status",
    "physnemo__list_artifacts", "physnemo__get_artifact", "physnemo__render_artifacts"
)
assert "physnemo__render_artifacts" not in tuple(c.EXPECTED_TOOLS)
configured_yaml = c.render_nat_config("/s", "v2.2.2", "/a", "http://x", "x"*64, agent_configured=True)
unconfigured_yaml = c.render_nat_config("/s", "v2.2.2", "/a", "http://x", "x"*64, agent_configured=False)
assert 'agent_name: "physnemo_agent"' in configured_yaml
assert 'agent_name: null' in unconfigured_yaml
assert "Call physnemo__render_artifacts" in c.PLUGIN_REGISTER
assert "agent_name: FunctionRef | None = None" in c.PLUGIN_REGISTER
assert "from nat.data_models.component_ref import FunctionRef" in c.PLUGIN_REGISTER
assert "upload_file_to_openwebui" not in c.PLUGIN_REGISTER
assert 'ToolCall="python"' not in c.PLUGIN_REGISTER
source_text = __import__("pathlib").Path(p).read_text(encoding="utf-8")
assert "--openwebui-database" in source_text
assert "chat_tool_execution_ready" in source_text
assert "/openwebui-api/chat/completions" in source_text
assert "PHYSNEMO_GATEWAY_ROUTE" in source_text
assert "_EngineeringMCPRequest" in source_text
assert m.PHYSNEMO_OPENAPI_OPERATION_ID_CONTRACT == "OPENAPI_PATH_AND_OPERATION_ID_UNION_V1"
assert m.PHYSNEMO_OPENAPI_CANONICAL_ID_CONTRACT == "OPENAPI_CANONICAL_MCP_OPERATION_IDS_V1"
assert m.OPENWEBUI_NATIVE_DATABASE_SYNC_CONTRACT == "OPENWEBUI_NATIVE_SQLITE_LIVE_SYNC_V1"
assert m.OPENWEBUI_MANAGED_API_KEY_CONTRACT == "OPENWEBUI_MANAGED_API_KEY_V1"
assert m.OPENWEBUI_DLP_PREFLIGHT_CONTRACT == "OPENWEBUI_DLP_GLOBAL_FILTER_REPAIR_V1"
assert m.OPENWEBUI_PHYSNEMO_READINESS_CONTRACT == "OPENWEBUI_PHYSNEMO_TOOL_EXECUTION_READINESS_V1"
assert m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_CONTRACT == "OPENWEBUI_GLOBAL_FILTER_TOOL_ID_INJECTION_V1"
assert m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_FILTER_CONTRACT == "ENGINEERING_MCP_TOOL_ROUTER_FILTER_V1"
router_test = m._engineering_tool_router_self_test(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE)
assert router_test["ok"] and all(router_test["checks"].values())
# Reproduce the v2.9.9 failure under a Python where Pydantic is unavailable.
import builtins
_real_import = builtins.__import__
_saved_pydantic = sys.modules.pop("pydantic", None)
def _without_pydantic(name, *args, **kwargs):
    if name == "pydantic" and name not in sys.modules:
        raise ModuleNotFoundError("No module named 'pydantic'", name="pydantic")
    return _real_import(name, *args, **kwargs)
builtins.__import__ = _without_pydantic
try:
    shim_router_test = m._engineering_tool_router_self_test(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE)
finally:
    builtins.__import__ = _real_import
    if _saved_pydantic is not None:
        sys.modules["pydantic"] = _saved_pydantic
assert shim_router_test["ok"] and all(shim_router_test["checks"].values())
assert shim_router_test["dependency_mode"] == "stdlib-self-test-shim"
assert (("pydantic" in sys.modules) if _saved_pydantic is not None else ("pydantic" not in sys.modules))
assert callable(m._sync_openwebui_engineering_tool_router)
assert callable(m._discover_openwebui_sqlite)
assert callable(m._ensure_openwebui_managed_api_key)
assert callable(m.sync_physnemo_openwebui_tool_server)
class _Route:
    operation_id = None
    path_format = "/physnemo__solve"
    path = path_format
    name = "tool"
    methods = {"POST"}
assert m._engineering_openapi_operation_id(_Route()) == "physnemo__solve"
class _Explicit(_Route):
    operation_id = "physnemo__render_artifacts"
    path_format = "/render-artifacts"
assert m._engineering_openapi_operation_id(_Explicit()) == "physnemo__render_artifacts"
paths = {
    "/physnemo__environment_info": {"post": {"operationId": "physnemo__environment_info"}},
    "/physnemo__solve": {"post": {"operationId": "physnemo__solve"}},
    "/physnemo__job_status": {"post": {"operationId": "physnemo__job_status"}},
    "/physnemo__list_artifacts": {"post": {"operationId": "physnemo__list_artifacts"}},
    "/physnemo__get_artifact": {"post": {"operationId": "physnemo__get_artifact"}},
    "/render-artifacts": {"post": {"operationId": "physnemo__render_artifacts"}},
}
tool_paths, path_names, operation_ids, operation_map = m._openapi_tool_inventory(paths)
assert len(tool_paths) == 6
assert "physnemo__solve" in path_names and "render-artifacts" in path_names
assert "physnemo__render_artifacts" in operation_ids
assert operation_map["/render-artifacts"] == ["physnemo__render_artifacts"]
assert not m.missing_required_tool_groups("physnemo", path_names | operation_ids)
raw=zlib.decompress(base64.b85decode(m.PHYSNEMO_COMPONENT_B85.encode("ascii")))
assert hashlib.sha256(raw).hexdigest() == expected
sample=json.dumps({"result": json.dumps({"job_id":"job-20260919T120000Z-0123456789ab","state":"completed"})}).encode()
assert m._physnemo_completed_job_id_from_tool_response(sample) == "job-20260919T120000Z-0123456789ab"
'@
        & $exe @prefix -W error -c $code $tempPython $ExpectedComponentSha256
        if ($LASTEXITCODE -ne 0) { continue }
        $PythonChecked = $true
        break
    }
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not $PythonChecked) {
    Fail-Verification "Nebyl nalezen kompatibilní Python nebo dynamická kontrola bootstrapu selhala."
}

Write-Host "PASS: SHA-256 jednotného instalátoru souhlasí." -ForegroundColor Green
Write-Host "PASS: PowerShell AST je bez chyb a zachovává všech 46 parametrů." -ForegroundColor Green
Write-Host "PASS: vložený Python a PhysicsNeMo komponent 1.2.10 prošly integritní kontrolou." -ForegroundColor Green
Write-Host "PASS: spravovaný artifacts kořen, obecný solve, inline galerie a živá Open WebUI synchronizace jsou přítomné." -ForegroundColor Green
Write-Host "PASS: OpenAPI operationId, nativní SQLite/API sync, managed API key, DLP preflight a globální Engineering MCP tool router jsou přítomné." -ForegroundColor Green
Write-Host "PASS: Python bootstrap prošel py_compile a dynamickou kontrolou." -ForegroundColor Green
Write-Host "PASS: JSON/SSE adaptér a vložený LangChain preflight jsou součástí instalátoru." -ForegroundColor Green
Write-Host "Poznámka: tato kontrola balíčku nenahrazuje živý WSL/modelový preflight při Install/Resume."
