"""APA 7 citations and references, plus the source list Word uses for its citation fields."""
from __future__ import annotations

import re
import unicodedata
import uuid

from . import i18n

TYPES = {"book": "Book", "report": "Report", "standard": "Report", "web": "InternetSite",
         "article": "JournalArticle", "law": "Misc", "other": "Misc"}
B_NS = "http://schemas.openxmlformats.org/officeDocument/2006/bibliography"


class CitationError(Exception):
    pass


def normalise(source: dict) -> dict:
    """Checked copy of a source with its authors as (family, given) pairs."""
    if not isinstance(source, dict) or not source.get("id"):
        raise CitationError(f"every source needs an 'id': {source!r}")
    out = dict(source)
    out["id"] = str(source["id"])
    out["type"] = str(source.get("type") or "other")
    if out["type"] not in TYPES:
        raise CitationError(f"source '{out['id']}': unknown type '{out['type']}' (use {', '.join(TYPES)})")
    authors = []
    for author in source.get("authors") or []:
        if isinstance(author, dict):
            authors.append((str(author.get("family") or "").strip(), str(author.get("given") or "").strip()))
        else:
            family, _, given = str(author).partition(",")
            authors.append((family.strip(), given.strip()))
    out["authors"] = authors
    out["organization"] = str(source.get("organization") or "")
    if not authors and not out["organization"]:
        raise CitationError(f"source '{out['id']}' needs 'authors' or 'organization'")
    if not source.get("title"):
        raise CitationError(f"source '{out['id']}' needs a 'title'")
    out["title"] = str(source["title"]).rstrip(".")
    out["year"] = str(source.get("year") or "n.d.")
    return out


def tag(source_id: str) -> str:
    """Identifier Word accepts for a source: letters and digits only."""
    return re.sub(r"[^A-Za-z0-9]", "", source_id) or "Source"


def _initials(given: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", given) if p]
    return " ".join(p[0].upper() + "." for p in parts)


def _reference_authors(source: dict) -> str:
    if not source["authors"]:
        return source["organization"]
    names = [f"{family}, {_initials(given)}".rstrip(", ") for family, given in source["authors"]]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def in_text(source: dict) -> str:
    """Author-date text of a parenthetical citation, without the parentheses."""
    if source.get("cite"):
        return str(source["cite"])
    families = [family for family, _ in source["authors"]]
    if not families:
        who = source["organization"]
    elif len(families) == 1:
        who = families[0]
    elif len(families) == 2:
        who = f"{families[0]} & {families[1]}"
    else:
        who = f"{families[0]} et al."
    return f"{who}, {source['year']}"


def reference_runs(source: dict, lang: str) -> list[tuple[str, bool]]:
    """The reference entry as (text, italic) runs."""
    if source.get("apa"):
        return [(str(source["apa"]), False)]
    authors = _reference_authors(source)
    head = f"{authors}{'' if authors.endswith('.') else '.'} ({source['year']}). "
    extras = []
    if source.get("edition"):
        extras.append(i18n.ordinal_edition(source["edition"], lang))
    if source.get("number"):
        extras.append(str(source["number"]))
    paren = f" ({'; '.join(extras)})" if extras else ""
    runs: list[tuple[str, bool]] = [(head, False)]
    if source["type"] == "article":
        runs.append((source["title"] + ". ", False))
        journal = str(source.get("journal") or "")
        if journal:
            volume = f", {source['volume']}" if source.get("volume") else ""
            runs.append((journal + volume, True))
            issue = f"({source['issue']})" if source.get("issue") else ""
            pages = f", {source['pages']}" if source.get("pages") else ""
            runs.append((f"{issue}{pages}. ", False))
    else:
        runs.append((source["title"], True))
        runs.append((paren + ". ", False))
        publisher = str(source.get("publisher") or source.get("site") or "")
        if publisher and publisher != source["organization"]:
            runs.append((publisher + ". ", False))
    link = source.get("doi") or source.get("url")
    if link:
        link = str(link)
        if source.get("doi") and not link.startswith("http"):
            link = "https://doi.org/" + link
        runs.append((link, False))
    text_end = runs[-1][0].rstrip()
    runs[-1] = (text_end, runs[-1][1])
    return runs


def sort_key(source: dict) -> str:
    first = source["authors"][0][0] if source["authors"] else source["organization"]
    folded = unicodedata.normalize("NFD", f"{first} {source['year']} {source['title']}")
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Mn").lower()


def sources_xml(sources: list[dict]) -> bytes:
    """The bibliography part Word reads to manage sources and to refresh citation fields."""
    def esc(text) -> str:
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<b:Sources xmlns:b="{B_NS}" xmlns="{B_NS}" SelectedStyle="\\APASixthEditionOfficeOnline.xsl" '
           'StyleName="APA" Version="6">']
    for order, source in enumerate(sources, 1):
        out.append(f"<b:Source><b:Tag>{tag(source['id'])}</b:Tag><b:SourceType>{TYPES[source['type']]}</b:SourceType>")
        out.append("<b:Guid>{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "sedocs:" + source["id"])).upper() + "}</b:Guid>")
        out.append("<b:Author><b:Author>")
        if source["authors"]:
            out.append("<b:NameList>")
            for family, given in source["authors"]:
                out.append(f"<b:Person><b:Last>{esc(family)}</b:Last><b:First>{esc(given)}</b:First></b:Person>")
            out.append("</b:NameList>")
        else:
            out.append(f"<b:Corporate>{esc(source['organization'])}</b:Corporate>")
        out.append("</b:Author></b:Author>")
        out.append(f"<b:Title>{esc(source['title'])}</b:Title><b:Year>{esc(source['year'])}</b:Year>")
        for key, element in (("publisher", "Publisher"), ("edition", "Edition"), ("journal", "JournalName"),
                             ("volume", "Volume"), ("issue", "Issue"), ("pages", "Pages"), ("url", "URL"),
                             ("site", "InternetSiteTitle"), ("number", "StandardNumber")):
            if source.get(key):
                out.append(f"<b:{element}>{esc(source[key])}</b:{element}>")
        out.append(f"<b:RefOrder>{order}</b:RefOrder></b:Source>")
    out.append("</b:Sources>")
    return "".join(out).encode("utf-8")
