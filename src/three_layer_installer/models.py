"""Core domain types shared by planning, execution, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Layer(Enum):
    """The three functional layers in installation order."""

    RTK = (1, "RTK")
    LSP = (2, "Native LSP")
    JMUNCH = (3, "jMunch")

    def __new__(cls, value: int, label: str) -> Layer:
        member = object.__new__(cls)
        member._value_ = value
        member.label = label
        return member

    label: str


class Status(str, Enum):
    ACTIVE = "ACTIVE"
    CONFIGURED = "CONFIGURED"
    GUIDANCE_ONLY = "GUIDANCE ONLY"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNAVAILABLE_FROM_CLIENT = "UNAVAILABLE FROM CLIENT"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ClientId(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    COPILOT = "copilot"
    GEMINI = "gemini"
    QWEN = "qwen"
    KIMI = "kimi"
    KILO = "kilo"
    KIRO = "kiro"
    ANTIGRAVITY = "antigravity"
    VSCODE = "vscode"


class VerificationScope(str, Enum):
    CLIENT_NATIVE = "client-native"
    SERVER_PROTOCOL = "server-protocol"
    CONFIG_ONLY = "config-only"
    NONE = "none"


class JMunchUse(str, Enum):
    NONCOMMERCIAL = "noncommercial"
    COMMERCIAL_LICENSED = "commercial-licensed"
    SKIP = "skip"


@dataclass(frozen=True)
class LayerResult:
    client: ClientId
    layer: Layer
    status: Status
    message: str
    components: dict[str, Status] = field(default_factory=dict)
    verification_scope: VerificationScope = VerificationScope.NONE

