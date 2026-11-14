# Document spec

`sedocs build document.yaml [-o file.docx]` builds a Word document. Paths in the spec are relative to the spec file. Without `-o` the result goes to `out/<spec name>.docx`.

```yaml
document:
  title: Use Case Specification          # required
  responsible:                           # required: who answers for the document
    - {name: Jane Doe, role: Business analyst}
  date: 2026-03-02                       # required; a YAML date is written out in the output language
  project: Appointment Booking System    # default: project.name of the model
  organization: Harbor Vet Clinic        # optional; default: project.organization
  version: "1.0"                         # optional
  status: Draft                          # optional
  language: en                           # optional: en or es; default: the model's language
model: project.yaml                      # needed by model blocks and diagrams
profile: default                         # default | path to a profile YAML | inline mapping
sources: [...]                           # see Sources
sections:
  - heading: Introduction
    page_break: false                    # optional: start the section on a new page
    content: [...]                       # blocks, in order
    sections: [...]                      # nested sections, up to three levels
```

## Content blocks

A block is plain text (a paragraph) or a mapping with one key.

| Block | Value |
|-------|-------|
| `paragraph` | Text. Inline marks: `**bold**`, `*italic*`, `{cite:source-id}` or `{cite:a,b}` |
| `bullets`, `numbered` | List of texts |
| `table` | `title`, `columns`, `rows`; optional `widths` (relative), `center` (column indexes), `source` |
| `figure` | `title` plus `path` (image file) or `diagram`; optional `width_in`, `source` |
| `page_break` | `true` |
| `references` | `true`, or `{include_uncited: true}`; lists the cited sources in APA 7 order |
| `actors_table` | Title text, or `{title, source}` |
| `requirements_table` | `functional` or `non_functional`, or `{kind, title, source}` |
| `business_rules_table` | Title text, or `{title, source}` |
| `use_case_table` | Module id, or `{module, title, source}`; without a module it lists every use case |
| `use_case_card` | Use case id, or `{id, title, source}` |
| `use_case_cards` | `{module: M1}` or `{}` for all; one card per use case |
| `traceability_table` | Title text; functional requirements against use cases and business rules |

`diagram` is the id of an entry under `diagrams` in the model, or inline: `{type: usecase, module: M1, use_cases: [...], title: ..., positions: {...}, show_ids: true, neighbors: false}` or `{type: context, title: ...}`.

`source` on a table or figure overrides the profile: `true` or `own` writes the standard source line, text writes that text, `false` writes none.

A table cell can hold several lines: separate them with a line break inside the text.

## Sources

```yaml
sources:
  - id: sommerville
    type: book                 # book | report | standard | web | article | law | other
    authors:                   # or organization: Name of the body
      - {family: Sommerville, given: Ian}
    year: 2016
    title: Software engineering
    edition: 10
    publisher: Pearson
    # number: ISO/IEC 25010:2011   journal, volume, issue, pages   url, doi, site
    # cite: "ISO, 2011"            overrides the in-text form
    # apa: "Full entry as text."   overrides the reference entry
```

Citations become Word citation fields and the reference list becomes Word's bibliography, so both can be managed from Word's References tab. Sources that are never cited are left out and reported as a warning.

## Profile

Settings and their defaults. Give only what changes.

```yaml
language: null                 # en | es; overrides the model, is overridden by document.language
template: null                 # .docx of the organisation: its styles, header and footer are used
content_marker: "{{content}}"  # paragraph of the template that the content replaces
page: {size: letter, margin_cm: 2.5}          # letter | a4; ignored with a template
fonts: {body: Arial, size: 11}                # ignored with a template
paragraph: {align: justify, line_spacing: 1.15, space_after: 8}
colors: {accent: "374151", header_text: "FFFFFF", label_fill: "F3F4F6", border: "9CA3AF", muted: "6B7280"}
headings: {numbered: true}     # set false when the template numbers its own headings
captions: {position: above, source_line: false, size: 9}   # source_line: true | false | text
tables: {font_size: 9, justify_wide: false, wide_percent: 30}
figures: {max_width_in: 6.3, max_height_in: 7.5}
citations: {word_fields: true}
cover: {enabled: auto, logo: null}   # auto: built-in cover unless a template is used
toc: false
```

## Templates of an organisation

- Placeholders replaced anywhere in the template, including headers and footers: `{{title}}`, `{{project}}`, `{{organization}}`, `{{responsible}}`, `{{date}}`, `{{version}}`, `{{status}}`.
- A paragraph containing only `{{content}}` marks where the sections go. Without it they are appended at the end.
- Headings use the template's "Heading 1" to "Heading 3" styles.
- The built-in cover is off with a template; turn it on with `cover: {enabled: true}`.

## Checking the result

- `sedocs inspect file.docx` prints the outline, every caption with its position and any `PROBLEM` (unresolved marker, caption away from its object, citation without source). Exit code 1 when there is a problem.
- `sedocs preview file.docx` writes a PDF and one PNG per page. Pagination comes from LibreOffice and is close to Word's, not identical: do not tune page breaks to the last line.
