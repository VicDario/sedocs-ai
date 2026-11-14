"""The project model: one YAML file that every artefact is generated from.

The model holds the actors, requirements, business rules, modules and use cases of a project.
`validate` reports broken references and gaps, so that diagrams, tables and cards stay consistent.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import i18n


class ModelError(Exception):
    """The file cannot be read as a project model at all."""


@dataclass(frozen=True)
class Issue:
    level: str  # "error" or "warning"
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code}: {self.message}"


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _text_list(value) -> list[str]:
    return [str(item) for item in _as_list(value)]


class Project:
    """Normalised view of a project model."""

    def __init__(self, data: dict[str, Any], path: Path | None = None):
        if not isinstance(data, dict):
            raise ModelError("the project model must be a YAML mapping")
        self.path = path
        self.data = data
        meta = data.get("project") or {}
        if not isinstance(meta, dict):
            raise ModelError("'project' must be a mapping with at least 'name'")
        self.name: str = str(meta.get("name") or "")
        self.organization: str = str(meta.get("organization") or "")
        try:
            self.language: str = i18n.language(meta.get("language"))
        except ValueError as exc:
            raise ModelError(str(exc)) from exc

        self.actors = [self._actor(a) for a in self._mappings("actors", data.get("actors"))]
        reqs = data.get("requirements") or {}
        if not isinstance(reqs, dict):
            raise ModelError("'requirements' must be a mapping with 'functional' and 'non_functional'")
        self.functional = [self._requirement(r) for r in self._mappings("requirements.functional", reqs.get("functional"))]
        self.non_functional = [self._requirement(r) for r in self._mappings("requirements.non_functional", reqs.get("non_functional"))]
        self.business_rules = [self._rule(r) for r in self._mappings("business_rules", data.get("business_rules"))]
        self.modules = [dict(m) for m in self._mappings("modules", data.get("modules"))]
        self.use_cases = [self._use_case(u) for u in self._mappings("use_cases", data.get("use_cases"))]
        self.team = [dict(m) for m in self._mappings("team", data.get("team"))]
        context = data.get("context") or {}
        self.context_flows = [dict(f) for f in self._mappings("context.flows", context.get("flows") if isinstance(context, dict) else None)]
        self.diagrams = [dict(d) for d in self._mappings("diagrams", data.get("diagrams"))]

    # ------------------------------------------------------------------ parsing
    @staticmethod
    def _mappings(where: str, value) -> list[dict]:
        items = _as_list(value)
        for item in items:
            if not isinstance(item, dict):
                raise ModelError(f"every entry of '{where}' must be a mapping, found: {item!r}")
        return items

    @staticmethod
    def _actor(raw: dict) -> dict:
        actor = dict(raw)
        actor["id"] = str(raw.get("id") or "")
        actor["name"] = str(raw.get("name") or "")
        actor["kind"] = str(raw.get("kind") or "human")
        actor["type"] = str(raw.get("type") or "primary")
        return actor

    @staticmethod
    def _requirement(raw: dict) -> dict:
        req = dict(raw)
        req["id"] = str(raw.get("id") or "")
        req["name"] = str(raw.get("name") or "")
        req["actors"] = _text_list(raw.get("actors"))
        return req

    @staticmethod
    def _rule(raw: dict) -> dict:
        rule = dict(raw)
        rule["id"] = str(raw.get("id") or "")
        rule["requirements"] = _text_list(raw.get("requirements"))
        return rule

    @staticmethod
    def _use_case(raw: dict) -> dict:
        uc = dict(raw)
        uc["id"] = str(raw.get("id") or "")
        uc["name"] = str(raw.get("name") or "")
        uc["module"] = str(raw["module"]) if raw.get("module") is not None else ""
        uc["actors"] = _text_list(raw.get("actors"))
        uc["requirements"] = _text_list(raw.get("requirements"))
        uc["includes"] = _text_list(raw.get("includes"))
        extends = []
        for item in _as_list(raw.get("extends")):
            if isinstance(item, dict):
                extends.append({"target": str(item.get("target") or ""), "condition": str(item.get("condition") or "")})
            else:
                extends.append({"target": str(item), "condition": ""})
        uc["extends"] = extends
        uc["specializes"] = str(raw["specializes"]) if raw.get("specializes") else ""
        for key in ("preconditions", "postconditions", "main_flow", "alternative_flows", "exceptions"):
            uc[key] = _text_list(raw.get(key))
        return uc

    # ------------------------------------------------------------------ lookups
    def actor(self, actor_id: str) -> dict | None:
        return next((a for a in self.actors if a["id"] == actor_id), None)

    def use_case(self, uc_id: str) -> dict | None:
        return next((u for u in self.use_cases if u["id"] == uc_id), None)

    def module(self, module_id: str) -> dict | None:
        return next((m for m in self.modules if str(m.get("id")) == module_id), None)

    def requirement(self, req_id: str) -> dict | None:
        return next((r for r in self.functional + self.non_functional if r["id"] == req_id), None)

    def use_cases_of(self, module_id: str | None) -> list[dict]:
        if module_id is None:
            return list(self.use_cases)
        return [u for u in self.use_cases if u["module"] == module_id]

    def relations_text(self, uc: dict) -> str:
        """Relations of a use case as text, for the tables and cards."""
        parts = [f"«include» → {target}" for target in uc["includes"]]
        for ext in uc["extends"]:
            cond = f" {{{ext['condition']}}}" if ext["condition"] else ""
            parts.append(f"«extend» → {ext['target']}{cond}")
        if uc["specializes"]:
            parts.append(f"{i18n.t(self.language, 'generalizes')} {uc['specializes']}")
        return "\n".join(parts)


def load_project(path: str | Path) -> Project:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelError(f"project model not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ModelError(f"project model cannot be read: {path} ({exc})") from exc
    except yaml.YAMLError as exc:
        raise ModelError(f"{path} is not valid YAML: {exc}") from exc
    return Project(data or {}, path)


# ---------------------------------------------------------------------- validation
def _duplicates(ids: list[str]) -> list[str]:
    seen, repeated = set(), []
    for item in ids:
        if item in seen and item not in repeated:
            repeated.append(item)
        seen.add(item)
    return repeated


def _cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """First cycle found in a directed graph, as the list of nodes on it."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if nxt in graph and state.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def validate(project: Project) -> list[Issue]:
    issues: list[Issue] = []

    def error(code: str, message: str) -> None:
        issues.append(Issue("error", code, message))

    def warning(code: str, message: str) -> None:
        issues.append(Issue("warning", code, message))

    if not project.name:
        error("missing-field", "project.name is required")

    collections = {
        "actor": project.actors,
        "requirement": project.functional + project.non_functional,
        "business rule": project.business_rules,
        "module": project.modules,
        "use case": project.use_cases,
    }
    for label, items in collections.items():
        ids = [str(item.get("id") or "") for item in items]
        for index, item_id in enumerate(ids):
            if not item_id:
                error("missing-field", f"{label} number {index + 1} has no id")
        for item_id in _duplicates([i for i in ids if i]):
            error("duplicate-id", f"{label} id '{item_id}' is used more than once")
        if label != "business rule":
            for item in items:
                if item.get("id") and not item.get("name"):
                    error("missing-field", f"{label} '{item['id']}' has no name")

    actor_ids = {a["id"] for a in project.actors}
    functional_ids = {r["id"] for r in project.functional}
    requirement_ids = functional_ids | {r["id"] for r in project.non_functional}
    module_ids = {str(m.get("id")) for m in project.modules}
    uc_ids = {u["id"] for u in project.use_cases}

    for actor in project.actors:
        if actor["kind"] not in ("human", "system"):
            error("invalid-value", f"actor '{actor['id']}': kind must be 'human' or 'system', not '{actor['kind']}'")
        if actor["type"] not in ("primary", "secondary", "external"):
            error("invalid-value", f"actor '{actor['id']}': type must be primary, secondary or external")
    for req in project.functional + project.non_functional:
        for actor_id in req["actors"]:
            if actor_id not in actor_ids:
                error("unknown-actor", f"requirement '{req['id']}' names actor '{actor_id}', which is not defined")
    for rule in project.business_rules:
        for req_id in rule["requirements"]:
            if req_id not in requirement_ids:
                error("unknown-requirement", f"business rule '{rule['id']}' names requirement '{req_id}', which is not defined")

    for uc in project.use_cases:
        uid = uc["id"]
        if uc["module"] and uc["module"] not in module_ids:
            error("unknown-module", f"use case '{uid}' belongs to module '{uc['module']}', which is not defined")
        for actor_id in uc["actors"]:
            if actor_id not in actor_ids:
                error("unknown-actor", f"use case '{uid}' names actor '{actor_id}', which is not defined")
        for req_id in uc["requirements"]:
            if req_id not in requirement_ids:
                error("unknown-requirement", f"use case '{uid}' names requirement '{req_id}', which is not defined")
        targets = [("includes", t) for t in uc["includes"]] + [("extends", e["target"]) for e in uc["extends"]]
        if uc["specializes"]:
            targets.append(("specializes", uc["specializes"]))
        for relation, target in targets:
            if target == uid:
                error("self-reference", f"use case '{uid}' {relation} itself")
            elif target not in uc_ids:
                error("unknown-use-case", f"use case '{uid}' {relation} '{target}', which is not defined")

    for relation, graph in (
        ("include", {u["id"]: u["includes"] for u in project.use_cases}),
        ("generalization", {u["id"]: [u["specializes"]] if u["specializes"] else [] for u in project.use_cases}),
    ):
        cycle = _cycle(graph)
        if cycle:
            error(f"{relation}-cycle", f"{relation} relations form a cycle: {' → '.join(cycle)}")

    for flow in project.context_flows:
        stray = sorted(str(key) for key in set(flow) - {"actor", "direction", "label"})
        if stray:
            error("unknown-key", f"context flow '{flow.get('label', '')}' has unknown key(s) {', '.join(stray)}; "
                                 "quote a label that contains a comma or a colon")
        if not str(flow.get("label") or "").strip():
            error("missing-field", f"a context flow of actor '{flow.get('actor')}' has no label")
        if str(flow.get("actor") or "") not in actor_ids:
            error("unknown-actor", f"context flow '{flow.get('label', '')}' names actor '{flow.get('actor')}', which is not defined")
        if flow.get("direction") not in ("in", "out"):
            error("invalid-value", f"context flow '{flow.get('label', '')}': direction must be 'in' or 'out'")

    # Gaps: nothing is broken, but the model is probably incomplete.
    covered = {req for uc in project.use_cases for req in uc["requirements"]}
    for req in project.functional:
        if req["id"] and req["id"] not in covered:
            warning("uncovered-requirement", f"functional requirement '{req['id']}' is not covered by any use case")
    used_actors = {a for uc in project.use_cases for a in uc["actors"]}
    for actor in project.actors:
        if actor["id"] and actor["id"] not in used_actors:
            warning("unused-actor", f"actor '{actor['id']}' does not take part in any use case")
    reached = {t for uc in project.use_cases for t in uc["includes"]}
    for uc in project.use_cases:
        attached = uc["actors"] or uc["extends"] or uc["specializes"] or uc["id"] in reached
        if uc["id"] and not attached:
            warning("orphan-use-case", f"use case '{uc['id']}' has no actor and no other use case includes it")
        if uc["id"] and not uc["requirements"]:
            warning("untraced-use-case", f"use case '{uc['id']}' is not linked to any requirement")
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == "error" for issue in issues)
