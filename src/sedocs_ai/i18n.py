"""Labels of the generated artefacts in the supported output languages."""
from __future__ import annotations

import datetime as _dt

LANGUAGES = ("en", "es")

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "table": "Table",
        "figure": "Figure",
        "source_own": "Source: prepared by the authors ({year}).",
        "responsible": "Responsible",
        "date": "Date",
        "version": "Version",
        "status": "Status",
        "references": "References",
        "contents": "Contents",
        "toc_hint": "Update this table of contents in Word (right-click, Update field).",
        "system_stereotype": "«system»",
        "id": "ID",
        "name": "Name",
        "description": "Description",
        "actors": "Actors",
        "actor": "Actor",
        "kind": "Kind",
        "category": "Category",
        "requirement": "Requirement",
        "requirements": "Requirements",
        "rule": "Business rule",
        "use_case": "Use case",
        "use_cases": "Use cases",
        "relations": "Relations",
        "module": "Module",
        "purpose": "Purpose",
        "preconditions": "Preconditions",
        "postconditions": "Postconditions",
        "main_flow": "Main flow",
        "alternative_flows": "Alternative flows",
        "exceptions": "Exceptions",
        "business_rules": "Business rules",
        "use_case_card": "Use case card",
        "none": "—",
        "human": "Person",
        "system": "System",
        "generalizes": "Specializes",
        "edition": "{n} ed.",
        "retrieved": "",
        "lcid": "1033",
    },
    "es": {
        "table": "Tabla",
        "figure": "Figura",
        "source_own": "Fuente: elaboración propia ({year}).",
        "responsible": "Responsable",
        "date": "Fecha",
        "version": "Versión",
        "status": "Estado",
        "references": "Referencias",
        "contents": "Contenido",
        "toc_hint": "Actualice esta tabla de contenido en Word (clic derecho, Actualizar campo).",
        "system_stereotype": "«sistema»",
        "id": "ID",
        "name": "Nombre",
        "description": "Descripción",
        "actors": "Actores",
        "actor": "Actor",
        "kind": "Tipo",
        "category": "Categoría",
        "requirement": "Requerimiento",
        "requirements": "Requerimientos",
        "rule": "Regla de negocio",
        "use_case": "Caso de uso",
        "use_cases": "Casos de uso",
        "relations": "Relaciones",
        "module": "Módulo",
        "purpose": "Propósito",
        "preconditions": "Precondiciones",
        "postconditions": "Postcondiciones",
        "main_flow": "Flujo básico",
        "alternative_flows": "Flujos alternativos",
        "exceptions": "Excepciones",
        "business_rules": "Reglas de negocio",
        "use_case_card": "Ficha del caso de uso",
        "none": "—",
        "human": "Persona",
        "system": "Sistema",
        "generalizes": "Especializa a",
        "edition": "{n} ed.",
        "retrieved": "",
        "lcid": "3082",
    },
}

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"],
}


def language(code: str | None) -> str:
    code = (code or "en").lower()[:2]
    if code not in LANGUAGES:
        raise ValueError(f"unsupported language '{code}': use one of {', '.join(LANGUAGES)}")
    return code


def t(lang: str, key: str, **values) -> str:
    text = LABELS[language(lang)][key]
    return text.format(**values) if values else text


def format_date(value, lang: str) -> str:
    """Dates given as YAML dates are written out in the output language; text is kept as given."""
    if isinstance(value, _dt.datetime):
        value = value.date()
    if not isinstance(value, _dt.date):
        return str(value)
    month = _MONTHS[language(lang)][value.month - 1]
    if language(lang) == "es":
        return f"{value.day} de {month} de {value.year}"
    return f"{month} {value.day}, {value.year}"


def ordinal_edition(edition, lang: str) -> str:
    """'2' becomes '2nd ed.' in English and '2.ª ed.' in Spanish; other text is kept as given."""
    text = str(edition).strip()
    if not text.isdigit():
        return text
    n = int(text)
    if language(lang) == "es":
        return f"{n}.ª ed."
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} ed."
