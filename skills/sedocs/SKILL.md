---
name: sedocs
description: "Trigger: software engineering document, requirements spec, SRS, use case spec, analysis document, sedocs. Plan and build engineering documents from one project model."
license: Apache-2.0
metadata:
  author: "VicDario"
  version: "0.1.0"
---

## Activation Contract

Load when the user asks for a software engineering document or several artefacts of one project: requirement tables, use case diagrams and cards, a context diagram, a traceability table, or the Word document that holds them.
For a single artefact go straight to the matching skill in Decision Gates.

## Hard Rules

- The project model (`project.yaml`) is the single source of truth. Never write an identifier, actor or requirement into a document that is not in the model.
- Never invent facts about the project. Ask the user, or mark an assumption as an assumption in the text.
- Run `sedocs check` after every model edit; do not build a document while it reports errors.
- A document needs a title, the responsible people and a date. Ask for them; never guess names.
- Keep earlier deliverables stable: extend the model and the specs, do not rewrite content the user already approved.
- Write the documents in the language of the model; keep one term per concept across artefacts.

## Decision Gates

| Need | Action |
|------|--------|
| `sedocs` command missing | Run `sedocs doctor`; if not found, follow `${CLAUDE_SKILL_DIR}/references/install.md` |
| No `project.yaml` yet | `sedocs init <dir>`, then fill the model from the user's material |
| Actors, use cases, diagrams, cards | Load skill `sedocs-use-cases` |
| Word document, cover, tables, citations, company template | Load skill `sedocs-document` |
| Artefact with no skill yet (activity, state, sequence, class diagram, test plan) | Say it is not covered in this version; offer a hand-written table or figure block |

## Execution Steps

1. Read what the user provided (brief, statement, rubric, earlier documents) and list the artefacts the deliverable needs.
2. Locate or create the model. Read `${CLAUDE_SKILL_DIR}/references/project-model.md` before editing it.
3. Update the model first, then run `sedocs check <model>` and fix every error; report warnings to the user.
4. Produce each artefact with its skill, in dependency order: requirements, use cases, diagrams, document.
5. Build with `sedocs build`, then `sedocs inspect` and `sedocs preview`; look at the page images before reporting.

## Output Contract

Return: files created or changed, the result of `sedocs check` (errors and warnings), the document path with its counts of tables, figures and citations, assumptions made, and what still needs the user's decision.

## References

- `references/project-model.md` — every field of the project model and the validation codes.
- `references/install.md` — installing the command-line tool and its optional system tools.
