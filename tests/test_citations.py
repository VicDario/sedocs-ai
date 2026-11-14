import xml.etree.ElementTree as ET

import pytest

from sedocs_ai import citations as C


def text(source, lang="en"):
    return "".join(run for run, _ in C.reference_runs(C.normalise(source), lang))


BOOK = {"id": "som11", "type": "book", "authors": [{"family": "Sommerville", "given": "Ian"}], "year": 2011,
        "title": "Software engineering", "edition": 9, "publisher": "Pearson"}
TWO = {"id": "pm", "type": "book", "authors": ["Pressman, Roger S.", "Maxim, Bruce R."], "year": 2020,
       "title": "Software engineering: A practitioner's approach", "edition": 9, "publisher": "McGraw-Hill"}
STANDARD = {"id": "iso-25010", "type": "standard", "organization": "International Organization for Standardization",
            "year": 2011, "title": "Systems and software quality models", "number": "ISO/IEC 25010:2011"}
ARTICLE = {"id": "a1", "type": "article", "authors": ["Boehm, Barry", "Basili, Victor R.", "Rombach, Dieter"],
           "year": 2001, "title": "Software defect reduction top 10 list", "journal": "Computer", "volume": 34,
           "issue": 1, "pages": "135-137", "doi": "10.1109/2.962984"}


def test_reference_entries_follow_apa_7():
    assert text(BOOK) == "Sommerville, I. (2011). Software engineering (9th ed.). Pearson."
    assert text(BOOK, "es") == "Sommerville, I. (2011). Software engineering (9.ª ed.). Pearson."
    assert text(TWO) == ("Pressman, R. S., & Maxim, B. R. (2020). Software engineering: A practitioner's approach "
                         "(9th ed.). McGraw-Hill.")
    assert text(STANDARD) == ("International Organization for Standardization. (2011). Systems and software quality "
                              "models (ISO/IEC 25010:2011).")
    assert text(ARTICLE) == ("Boehm, B., Basili, V. R., & Rombach, D. (2001). Software defect reduction top 10 list. "
                             "Computer, 34(1), 135-137. https://doi.org/10.1109/2.962984")


def test_titles_are_italic_where_apa_asks_for_it():
    assert [run for run, italic in C.reference_runs(C.normalise(BOOK), "en") if italic] == ["Software engineering"]
    assert [run for run, italic in C.reference_runs(C.normalise(ARTICLE), "en") if italic] == ["Computer, 34"]


def test_in_text_citations():
    assert C.in_text(C.normalise(BOOK)) == "Sommerville, 2011"
    assert C.in_text(C.normalise(TWO)) == "Pressman & Maxim, 2020"
    assert C.in_text(C.normalise(ARTICLE)) == "Boehm et al., 2001"
    assert C.in_text(C.normalise(STANDARD)) == "International Organization for Standardization, 2011"
    assert C.in_text(C.normalise({**STANDARD, "cite": "ISO, 2011"})) == "ISO, 2011"


def test_raw_overrides_and_sorting():
    assert text({**BOOK, "apa": "Custom entry."}) == "Custom entry."
    ordered = sorted((C.normalise(s) for s in (TWO, BOOK, STANDARD, ARTICLE)), key=C.sort_key)
    assert [s["id"] for s in ordered] == ["a1", "iso-25010", "pm", "som11"]


def test_invalid_sources_are_rejected():
    for bad in ({"title": "No id"}, {"id": "x", "title": "No author"}, {"id": "x", "organization": "Org"},
                {"id": "x", "organization": "Org", "title": "T", "type": "podcast"}):
        with pytest.raises(C.CitationError):
            C.normalise(bad)


def test_word_source_list_is_valid_xml():
    xml = C.sources_xml([C.normalise(s) for s in (BOOK, STANDARD, ARTICLE)])
    root = ET.fromstring(xml)
    tags = [el.text for el in root.iter(f"{{{C.B_NS}}}Tag")]
    assert tags == ["som11", "iso25010", "a1"]
