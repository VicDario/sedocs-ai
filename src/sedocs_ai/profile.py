"""Document profiles: the look and the rules of a family of documents.

A profile is a YAML mapping merged over DEFAULT. It can point to a Word template of the
organisation, set the output language, the caption position, the table look and so on.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULT: dict = {
    "name": "default",
    "language": None,                  # falls back to the document, then to the project model
    "template": None,                  # path to a .docx whose styles, header and footer are reused
    "content_marker": "{{content}}",   # paragraph of the template that the content replaces
    "page": {"size": "letter", "margin_cm": 2.5},
    "fonts": {"body": "Arial", "size": 11},
    "paragraph": {"align": "justify", "line_spacing": 1.15, "space_after": 8},
    "colors": {"accent": "374151", "header_text": "FFFFFF", "label_fill": "F3F4F6", "border": "9CA3AF",
               "muted": "6B7280"},
    "headings": {"numbered": True},
    "captions": {"position": "above", "source_line": False, "size": 9},
    "tables": {"font_size": 9, "justify_wide": False, "wide_percent": 30},
    "figures": {"max_width_in": 6.3, "max_height_in": 7.5},
    "citations": {"word_fields": True},
    "cover": {"enabled": "auto", "logo": None},   # auto: built-in cover unless a template is used
    "toc": False,
}


class ProfileError(Exception):
    pass


def _merge(base: dict, extra: dict, where: str = "profile") -> dict:
    for key, value in extra.items():
        if key not in base:
            raise ProfileError(f"unknown {where} setting '{key}' (known: {', '.join(sorted(base))})")
        if isinstance(base[key], dict) and isinstance(value, dict):
            _merge(base[key], value, f"{where}.{key}")
        else:
            base[key] = value
    return base


def load_profile(ref, base_dir: Path) -> dict:
    """`ref` is None or 'default', a path to a profile YAML file, or an inline mapping."""
    profile = copy.deepcopy(DEFAULT)
    anchor = Path(base_dir)
    if ref in (None, "default"):
        extra: dict = {}
    elif isinstance(ref, dict):
        extra = ref
    else:
        path = (anchor / str(ref)).resolve()
        if not path.is_file():
            raise ProfileError(f"profile not found: {path}")
        extra = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(extra, dict):
            raise ProfileError(f"{path} must contain a YAML mapping")
        anchor = path.parent
    _merge(profile, extra)
    for section, key in (("template", None), ("cover", "logo")):
        value = profile[section] if key is None else profile[section][key]
        if value:
            resolved = (anchor / str(value)).resolve()
            if not resolved.is_file():
                raise ProfileError(f"file named in the profile not found: {resolved}")
            if key is None:
                profile[section] = resolved
            else:
                profile[section][key] = resolved
    if profile["captions"]["position"] not in ("above", "below"):
        raise ProfileError("captions.position must be 'above' or 'below'")
    if profile["page"]["size"] not in ("letter", "a4"):
        raise ProfileError("page.size must be 'letter' or 'a4'")
    if profile["cover"]["enabled"] == "auto":
        profile["cover"]["enabled"] = profile["template"] is None
    return profile
