---
name: sedocs-document
description: "Trigger: Word document, docx, cover page, company template, captions, table of contents, APA references, citations. Assemble a Word document from a spec and the project model."
license: Apache-2.0
metadata:
  author: "VicDario"
  version: "0.1.0"
---

## Activation Contract

Load to create or update a Word document with `sedocs build`: cover, sections, tables, figures, model-driven blocks, citations, or a company template and its format rules.

## Hard Rules

- Change the spec (`document.yaml`) and rebuild. Never edit the generated `.docx` by hand.
- The cover needs `title`, `responsible` (name and optional role) and `date` from the user. Never invent people, roles or dates.
- Cite only sources you can identify with certainty: author, year, title. Never fabricate a reference; ask the user or leave the claim uncited.
- Refer to every table and figure in the text before it appears.
- Follow the format the organisation asks for through the profile (caption position, source line, template); do not hard-code it in the content.
- After building, run `sedocs inspect` and `sedocs preview` and look at the page images before reporting.

## Decision Gates

| Need | Action |
|------|--------|
| Organisation has a Word template | Set `profile.template`; put `{{title}}`, `{{responsible}}`, `{{date}}` and a `{{content}}` paragraph in it |
| Titles above tables and figures, source underneath | `profile.captions: {position: above, source_line: true}` |
| Spanish output | `document.language: es` or `language: es` in the model |
| Table of contents | `profile.toc: true`; tell the user Word fills it when the field is updated |
| Content comes from the model | Use model blocks (`requirements_table`, `use_case_table`, `use_case_cards`, `traceability_table`) instead of typing rows |
| Diagram of the model | `figure` block with `diagram: {type: usecase, module: M1}` or `{type: context}` |

## Execution Steps

1. Read `${CLAUDE_SKILL_DIR}/references/document-spec.md` for the spec, the blocks, sources and profile settings.
2. Create the spec with `sedocs init` or edit the existing one. Ask the user for the cover data that is missing.
3. Write the sections: plain paragraphs for prose, model blocks for anything the model already holds.
4. Run `sedocs build <spec>`; fix every error and resolve each `WARNING`.
5. Run `sedocs inspect <docx>` (must print no `PROBLEM`) and `sedocs preview <docx>`; open the page images.
6. Check: cover data, heading order, captions next to their object, no table row stranded alone on a page, references complete.

## Output Contract

Return: the `.docx` path, counts of tables, figures and cited sources, the `sedocs inspect` result, the number of pages seen in the preview, and anything the user must do in Word (update the table of contents, final review).

## References

- `references/document-spec.md` — spec format, content blocks, sources, profile settings and template placeholders.
