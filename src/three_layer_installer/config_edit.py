"""Source-preserving JSON/JSONC and TOML configuration edits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import tomlkit
from tomlkit.container import Container
from tomlkit.items import InlineTable, Table


class ConfigError(ValueError):
    """Configuration cannot be safely parsed or patched."""


@dataclass(frozen=True)
class _Token:
    kind: str
    start: int
    end: int
    text: str


@dataclass
class _Member:
    key: str
    value: _Node
    comma_end: int | None = None


@dataclass
class _Node:
    kind: str
    start: int
    end: int
    members: list[_Member] = field(default_factory=list)


def _tokens(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            if close < 0:
                raise ConfigError("invalid JSONC: unterminated block comment")
            index = close + 2
            continue
        if character in "{}[]:,":
            tokens.append(_Token(character, index, index + 1, character))
            index += 1
            continue
        if character == '"':
            end = index + 1
            escaped = False
            while end < len(text):
                current = text[end]
                if current == '"' and not escaped:
                    end += 1
                    break
                escaped = current == "\\" and not escaped
                end += 1
            else:
                raise ConfigError("invalid JSONC: unterminated string")
            raw = text[index:end]
            try:
                json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"invalid JSONC string: {exc}") from exc
            tokens.append(_Token("string", index, end, raw))
            index = end
            continue
        end = index
        while end < len(text) and not text[end].isspace() and text[end] not in "{}[]:,":
            if text.startswith(("//", "/*"), end):
                break
            end += 1
        if end == index:
            raise ConfigError(f"invalid JSONC near character {index}")
        raw = text[index:end]
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"invalid JSONC value near character {index}") from exc
        tokens.append(_Token("value", index, end, raw))
        index = end
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def current(self) -> _Token:
        if self.index >= len(self.tokens):
            raise ConfigError("invalid JSONC: unexpected end of document")
        return self.tokens[self.index]

    def take(self, kind: str | None = None) -> _Token:
        token = self.current()
        if kind is not None and token.kind != kind:
            raise ConfigError(f"invalid JSONC: expected {kind}, found {token.kind}")
        self.index += 1
        return token

    def parse(self) -> _Node:
        node = self.value()
        if self.index != len(self.tokens):
            raise ConfigError("invalid JSONC: content follows the root value")
        return node

    def value(self) -> _Node:
        token = self.current()
        if token.kind == "{":
            return self.object()
        if token.kind == "[":
            return self.array()
        if token.kind in {"string", "value"}:
            self.index += 1
            return _Node("value", token.start, token.end)
        raise ConfigError(f"invalid JSONC: unexpected token {token.kind}")

    def object(self) -> _Node:
        opening = self.take("{")
        members: list[_Member] = []
        if self.current().kind == "}":
            closing = self.take("}")
            return _Node("object", opening.start, closing.end, members)
        while True:
            key_token = self.take("string")
            key = json.loads(key_token.text)
            if not isinstance(key, str):
                raise ConfigError("invalid JSONC: object key must be a string")
            self.take(":")
            value = self.value()
            member = _Member(key, value)
            members.append(member)
            token = self.current()
            if token.kind == ",":
                member.comma_end = self.take(",").end
                if self.current().kind == "}":
                    closing = self.take("}")
                    return _Node("object", opening.start, closing.end, members)
                continue
            if token.kind == "}":
                closing = self.take("}")
                return _Node("object", opening.start, closing.end, members)
            raise ConfigError("invalid JSONC: expected comma or object close")

    def array(self) -> _Node:
        opening = self.take("[")
        if self.current().kind == "]":
            return _Node("array", opening.start, self.take("]").end)
        while True:
            self.value()
            token = self.current()
            if token.kind == ",":
                self.take(",")
                if self.current().kind == "]":
                    return _Node("array", opening.start, self.take("]").end)
                continue
            if token.kind == "]":
                return _Node("array", opening.start, self.take("]").end)
            raise ConfigError("invalid JSONC: expected comma or array close")


def _parse_jsonc(text: str) -> _Node:
    try:
        tokens = _tokens(text)
        if not tokens:
            raise ConfigError("invalid JSONC: document is empty")
        return _Parser(tokens).parse()
    except IndexError as exc:
        raise ConfigError("invalid JSONC: unexpected end of document") from exc


def _line_indent(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    prefix = text[start:position]
    return prefix if not prefix.strip() else ""


def _serialize(value: object, continuation_indent: str) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    lines = rendered.splitlines()
    return lines[0] + "".join(f"\n{continuation_indent}{line}" for line in lines[1:])


def _nested_value(path: tuple[str, ...], value: object) -> object:
    nested = value
    for key in reversed(path):
        nested = {key: nested}
    return nested


def _set_node(text: str, node: _Node, path: tuple[str, ...], value: object) -> str:
    if node.kind != "object":
        raise ConfigError(f"invalid JSONC: {'/'.join(path[:-1]) or 'root'} is not an object")
    key = path[0]
    member = next((item for item in node.members if item.key == key), None)
    if member is not None:
        if len(path) > 1:
            return _set_node(text, member.value, path[1:], value)
        indent = _line_indent(text, member.value.start)
        replacement = _serialize(value, indent)
        return text[: member.value.start] + replacement + text[member.value.end :]

    inserted_value = _nested_value(path[1:], value)
    closing = node.end - 1
    newline = "\r\n" if "\r\n" in text else "\n"
    parent_indent = _line_indent(text, closing)
    child_indent = (
        _line_indent(text, node.members[0].value.start)
        if node.members and _line_indent(text, node.members[0].value.start)
        else parent_indent + "  "
    )
    rendered = _serialize(inserted_value, child_indent + "  ")
    property_text = f'{child_indent}{json.dumps(key)}: {rendered}'

    if not node.members:
        insertion = f"{newline}{property_text}{newline}{parent_indent}"
        return text[: node.start + 1] + insertion + text[closing:]

    last = node.members[-1]
    compact = "\n" not in text[node.start:node.end]
    if compact:
        comma = "" if last.comma_end is not None else ","
        insertion = f'{comma} {json.dumps(key)}: {json.dumps(inserted_value, ensure_ascii=False)}'
        return text[:closing] + insertion + text[closing:]

    close_line_start = text.rfind("\n", node.start, closing) + 1
    comma_suffix = "," if last.comma_end is not None else ""
    prefix = text[:close_line_start]
    if last.comma_end is None:
        prefix = text[: last.value.end] + "," + text[last.value.end : close_line_start]
    insertion = f"{property_text}{comma_suffix}{newline}"
    return prefix + insertion + text[close_line_start:]


def set_jsonc_path(text: str, path: tuple[str, ...], value: object) -> str:
    if not path:
        raise ConfigError("JSONC path must not be empty")
    trailing_newline = "\r\n" if text.endswith("\r\n") else "\n" if text.endswith("\n") else ""
    source = text if text.strip() else "{}"
    root = _parse_jsonc(source)
    updated = _set_node(source, root, path, value)
    if trailing_newline and not updated.endswith(("\n", "\r")):
        updated += trailing_newline
    return updated


def set_toml_path(text: str, path: tuple[str, ...], value: object) -> str:
    if not path:
        raise ConfigError("TOML path must not be empty")
    try:
        document = tomlkit.parse(text)
    except (tomlkit.exceptions.ParseError, ValueError) as exc:
        raise ConfigError(f"invalid TOML: {exc}") from exc
    parent: Container | Table | InlineTable = document
    for key in path[:-1]:
        existing = parent.get(key)
        if existing is None:
            table = tomlkit.table()
            parent[key] = table
            parent = table
        elif isinstance(existing, (Container, Table, InlineTable)):
            parent = existing
        else:
            raise ConfigError(f"invalid TOML: {key} is not a table")
    parent[path[-1]] = tomlkit.item(value)
    return tomlkit.dumps(document)


def set_owned_block(text: str, block_id: str, content: str) -> str:
    if not block_id or any(character.isspace() for character in block_id):
        raise ConfigError("owned block identifier must be non-empty and contain no whitespace")
    start = f"<!-- three-layer:{block_id}:start -->"
    end = f"<!-- three-layer:{block_id}:end -->"
    block = f"{start}\n{content.rstrip()}\n{end}"
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index >= 0 or end_index >= 0:
        if start_index < 0 or end_index < start_index:
            raise ConfigError(f"owned block {block_id} is malformed")
        return text[:start_index] + block + text[end_index + len(end) :]
    separator = "" if not text else "\n" if text.endswith("\n") else "\n\n"
    return text + separator + block + "\n"
