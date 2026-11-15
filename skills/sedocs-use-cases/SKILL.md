---
name: sedocs-use-cases
description: "Trigger: use case, use case diagram, actors, context diagram, use case card, include, extend. Model use cases in the project model and draw their UML diagrams."
license: Apache-2.0
metadata:
  author: "VicDario"
  version: "0.1.0"
---

## Activation Contract

Load to identify actors and use cases, write use case cards, or draw a use case or context diagram for a project that has (or needs) a `project.yaml` model.

## Hard Rules

- Edit the model, never the drawing: diagrams and cards are generated from `project.yaml`.
- One use case is one goal of one actor, named verb plus object. Split any name that joins two goals with "and".
- Actors are roles or external systems, never named people and never the system itself.
- `includes` is behaviour that always runs; `extends` is optional behaviour and needs a `condition`; `specializes` is a kind of the parent. Do not use them to show order of execution.
- Every use case names at least one requirement and every functional requirement has a use case. `sedocs check` must end with 0 errors.
- Look at the rendered PNG before reporting a diagram as done.

## Decision Gates

| Situation | Action |
|-----------|--------|
| More than about 12 use cases in one diagram | Draw one diagram per module with `--module` |
| Render prints `WARNING ... crosses use case` | Add `positions` for that use case in a `diagrams` entry, render with `--diagram-id` |
| A use case is shared by two modules | Keep it in one module; related diagrams show it automatically |
| Steps of a flow look like use cases (open form, click save) | Put them in `main_flow`, not in the diagram |
| User asks for the diagram inside a document | Use a `figure` block with `diagram:`; load skill `sedocs-document` |

## Execution Steps

1. Read `${CLAUDE_SKILL_DIR}/references/use-case-guidelines.md` when writing or reviewing use cases.
2. Add or change actors, use cases and relations in the model; add `context.flows` for a context diagram.
3. Run `sedocs check <model>`; fix errors, then resolve or report each warning.
4. Render: `sedocs render usecase <model> --module M1 -o diagrams/uc-m1.png` or `sedocs render context <model> -o diagrams/context.png`.
5. Open the PNG. Fix crossings or crowded labels through the model and render again.
6. For cards, fill `purpose`, `preconditions`, `postconditions`, `main_flow`, `alternative_flows` and `exceptions`; they are printed by the document blocks `use_case_card` and `use_case_cards`.

## Output Contract

Return: use cases added or changed (id and name), the `sedocs check` summary line, paths of the diagrams rendered, remaining layout warnings, and any assumption made about the business.

## References

- `references/use-case-guidelines.md` — naming, relations, card writing and review checklist.
