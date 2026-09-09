"""
title: VUT AI Tutor
id: study_tutor_pipe
version: 1.26.2
required_open_webui_version: 0.10.0
author: OpenAI
description: Samostatná aktivní Pipe VUT AI Tutor pro Open WebUI Server i standalone Desktop; vyžaduje čerstvý Canvas Event runtime a izolovanou ASGI gateway v7; nemění hlavní router Open WebUI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PLUGIN_VERSION = '1.26.2'
TUTOR_BUILD_MARKER = 'VUT-AI-TUTOR-1.26.2-SERVER-DESKTOP-WINDOWS-MOCK-TRANSPORT-COMPLETE'
EXPECTED_BOOTSTRAP_ID = 'study_tutor_gateway_bootstrap'
EXPECTED_ROUTE_REGISTRATION_VERSION = 7


class Pipe:
    class Valves(BaseModel):
        DEFAULT_BASE_MODEL: str = Field(
            default="glm-5.2",
            description=(
                "Výchozí základní model. VUT AI Tutor hledá přesný model glm-5.2 "
                "i providerem prefixované varianty; uživatel jej může změnit v Canvasu."
            ),
        )
        RETRIEVAL_CHUNKS: int = Field(default=8, ge=3, le=16)
        AUTO_OPEN_CANVAS: bool = Field(
            default=True,
            description="Automaticky otevře VUT AI Tutor Canvas v pravém panelu při první běžné zprávě, přiložení PDF nebo nové Markdown učební cesty.",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def pipe(
        self,
        body: dict,
        __user__: dict | None = None,
        __request__=None,
        __event_emitter__=None,
        __event_call__=None,
        __metadata__: dict | None = None,
        __files__: list | None = None,
        __tools__: dict | None = None,
        __model__: dict | None = None,
        __skill_ids__: list | None = None,
        __chat_id__: str | None = None,
        __session_id__: str | None = None,
        __message_id__: str | None = None,
        __task__: str | None = None,
        __task_body__: dict | None = None,
        **kwargs,
    ):
        if __request__ is None:
            return "VUT AI Tutor potřebuje běžet uvnitř Open WebUI."
        runtime = getattr(__request__.app.state, "STUDY_TUTOR_RUNTIME", None)
        if runtime is None:
            return (
                "VUT AI Tutor Canvas runtime ještě nebyl inicializován. "
                f"V Admin Panelu aktivujte Event Function {EXPECTED_BOOTSTRAP_ID}."
            )
        runtime_version = str(getattr(runtime, "runtime_version", "") or "")
        runtime_marker = str(getattr(runtime, "build_marker", "") or "")
        if runtime_version != PLUGIN_VERSION or runtime_marker != TUTOR_BUILD_MARKER:
            return (
                "VUT AI Tutor odmítl použít zastaralý Canvas runtime "
                f"(runtime={runtime_version or 'unknown'}, Pipe={PLUGIN_VERSION}). "
                f"Spusťte úplný instalátor {EXPECTED_BOOTSTRAP_ID}; staré Tutor Event Function musí být deaktivovány nebo odstraněny."
            )
        register_routes = getattr(runtime, "register_routes", None)
        if callable(register_routes):
            try:
                await register_routes()
            except Exception as exc:
                return (
                    "VUT AI Tutor Canvas routy se nepodařilo zaregistrovat "
                    f"pomocí {EXPECTED_BOOTSTRAP_ID}: {type(exc).__name__}: {exc}"
                )
        route_state = getattr(__request__.app.state, "STUDY_TUTOR_ROUTE_DIAGNOSTICS", {})
        if isinstance(route_state, dict) and int(route_state.get("registration_version") or 0) != EXPECTED_ROUTE_REGISTRATION_VERSION:
            return (
                "VUT AI Tutor zjistil neplatnou verzi registrace Canvas rout: "
                f"{route_state.get('registration_version')!r}; očekáváno {EXPECTED_ROUTE_REGISTRATION_VERSION}."
            )
        metadata = dict(__metadata__ or {})
        for key, value in (
            ("chat_id", __chat_id__),
            ("session_id", __session_id__),
            ("message_id", __message_id__),
        ):
            if value and not metadata.get(key):
                metadata[key] = value
        return await runtime.handle_pipe(
            body=body,
            user_payload=__user__ or {},
            request=__request__,
            event_emitter=__event_emitter__,
            event_call=__event_call__,
            metadata=metadata,
            files=__files__ or [],
            available_tools=__tools__ or {},
            model_payload=__model__ or {},
            skill_ids=__skill_ids__ or kwargs.get("__skill_ids__") or [],
            default_base_model=self.valves.DEFAULT_BASE_MODEL,
            retrieval_chunks=self.valves.RETRIEVAL_CHUNKS,
            auto_open_canvas=self.valves.AUTO_OPEN_CANVAS,
            task=__task__,
            task_body=__task_body__,
        )
