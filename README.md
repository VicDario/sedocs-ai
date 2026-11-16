# sedocs-ai

[![CI](https://github.com/VicDario/sedocs-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/VicDario/sedocs-ai/actions/workflows/ci.yml)

Software engineering documents from a single project model.

You describe a project once, in one YAML file: actors, requirements, business rules, modules and use cases. `sedocs` validates that model and generates the artefacts from it: UML use case diagrams, a context diagram, requirement and traceability tables, use case cards, and the Word document that holds them. Because everything comes from the same model, identifiers and names stay consistent across the whole document.

The repository has two layers:

- **A command-line tool**, `sedocs`, that works on its own.
- **Agent skills** that teach an AI coding agent how to use the tool: what to ask, which rules to follow and how to check the result. They are packaged as a Claude Code plugin and are plain Markdown folders, so other agents can use them too.

Status: version 0.1, the first slice. See [Roadmap](#roadmap) for what is not covered yet.

## Install

The command-line tool, with [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/VicDario/sedocs-ai
sedocs doctor
```

The skills, as a Claude Code plugin:

```
/plugin install sedocs-ai --marketplace VicDario/sedocs-ai
```

On older versions of Claude Code, add the marketplace first:

```
/plugin marketplace add VicDario/sedocs-ai
/plugin install sedocs-ai@sedocs-ai
```

For another agent, copy the folders under `skills/` to wherever that agent reads skills from.

`sedocs doctor` lists the optional system tools: an SVG converter (librsvg, Inkscape or ImageMagick) for PNG diagrams and diagrams inside documents, and LibreOffice plus poppler for the PDF preview.

## Quick start

```
sedocs init docs                 # starter docs/project.yaml and docs/document.yaml
sedocs check docs/project.yaml   # validate the model
sedocs render usecase docs/project.yaml -o docs/diagrams/use-cases.png
sedocs build docs/document.yaml  # writes docs/out/document.docx
sedocs inspect docs/out/document.docx
sedocs preview docs/out/document.docx
```

A complete example with an invented company lives in [`examples/harbor-clinic`](examples/harbor-clinic):

```
sedocs build examples/harbor-clinic/document.yaml
```

## Commands

| Command | What it does |
|---------|--------------|
| `sedocs init [DIR] [--lang en\|es]` | Writes a starter project model and document spec |
| `sedocs check MODEL [--strict]` | Reports broken references as errors and coverage gaps as warnings |
| `sedocs render usecase MODEL -o FILE` | Use case diagram, laid out automatically; `--module`, `--use-cases`, `--diagram-id`, `--show-ids` |
| `sedocs render context MODEL -o FILE` | Context diagram with the data flows of each actor |
| `sedocs build SPEC [-o FILE.docx]` | Builds the Word document |
| `sedocs inspect FILE.docx` | Outline, captions and loose ends of a document |
| `sedocs preview FILE.docx` | PDF and one image per page |
| `sedocs doctor` | Which external tools are installed |

Diagram output is `.svg` or `.png`, chosen by the file extension.

## What the documents look like

- **Cover**: title, project, responsible people and date are required. Organisation, logo, version and status are optional. Nothing else is assumed.
- **Your organisation's template**: point the profile to a `.docx`; `{{title}}`, `{{responsible}}`, `{{date}}` and the other placeholders are filled in, and the content goes where the `{{content}}` paragraph is.
- **Captions**: numbered with Word caption fields, above or below the table or figure, with an optional source line.
- **Citations**: APA 7, as Word citation fields with a bibliography that Word can manage.
- **Language**: English or Spanish labels, set per project or per document.

The spec, the content blocks and the profile settings are documented in [`skills/sedocs-document/references/document-spec.md`](skills/sedocs-document/references/document-spec.md). The project model is documented in [`skills/sedocs/references/project-model.md`](skills/sedocs/references/project-model.md).

## Skills

| Skill | Use it for |
|-------|-----------|
| `sedocs` | Planning a deliverable and routing to the right skill; owns the project model rules |
| `sedocs-use-cases` | Actors, use cases, relations, cards, use case and context diagrams |
| `sedocs-document` | The Word document: cover, sections, tables, figures, citations, templates |

Each skill can be used alone. In Claude Code they are invoked as `/sedocs-ai:sedocs`, `/sedocs-ai:sedocs-use-cases` and `/sedocs-ai:sedocs-document`, or picked up automatically from the request.

## Roadmap

Not covered in this version:

- Activity, state, sequence and class diagrams, and the relational model.
- Planning artefacts: work breakdown structure, Gantt chart, responsibility matrix.
- A test plan skill and a rubric or checklist review skill.
- Slide decks.

Known limits: automatic layout handles two columns of use cases and reports any line that crosses a use case, to be fixed with manual positions; the table of contents is a Word field that Word fills in when it is updated.

## Development

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
claude plugin validate .
```

The examples and tests use invented companies and people only. `scripts/privacy_scan.py` rejects text shaped like a national ID number and any term from an optional local list, `.private/forbidden-terms.txt`, which is git-ignored. Every pull request runs the tests and this scan on GitHub; the term list is never published, so there the scan checks ID-shaped numbers only. To run it with your own list before every commit:

```
printf '#!/bin/sh\nexec python3 scripts/privacy_scan.py\n' > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

## License

Apache-2.0. See [LICENSE](LICENSE).
