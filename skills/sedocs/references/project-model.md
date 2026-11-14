# The project model

One YAML file, usually `project.yaml`, holds everything the artefacts are generated from. Create a starter with `sedocs init`. Validate with `sedocs check project.yaml` (add `--strict` to fail on warnings).

## Fields

```yaml
project:
  name: Appointment Booking System      # required
  organization: Harbor Vet Clinic       # optional, shown on covers
  language: en                          # en or es: language of every generated label

actors:
  - id: receptionist                    # used in references; never shown
    name: Receptionist                  # shown in diagrams and tables
    kind: human                         # human | system
    type: primary                       # primary | secondary | external
    description: Front-desk staff who book appointments.

requirements:
  functional:
    - {id: FR-01, name: Book appointment, description: "The system shall ...", actors: [receptionist]}
  non_functional:
    - {id: NFR-01, category: Performance, name: Response time, description: "... under 2 seconds ..."}

business_rules:
  - {id: BR-01, description: "An appointment needs a registered pet.", requirements: [FR-01]}

modules:
  - {id: M1, name: Scheduling}

use_cases:
  - id: UC-1.01
    name: Book appointment
    module: M1
    actors: [receptionist]
    requirements: [FR-01]
    includes: [UC-1.05]                 # this use case always runs UC-1.05
    extends:                            # this use case adds behaviour to the target, under a condition
      - {target: UC-1.02, condition: the slot is taken}
    specializes: UC-1.03                # this use case is a kind of UC-1.03
    purpose: ...
    description: ...
    preconditions: [...]
    postconditions: [...]
    main_flow: [...]                    # numbered automatically
    alternative_flows: ["1a. ..."]
    exceptions: ["4a. ..."]

context:
  flows:
    - {actor: receptionist, direction: in, label: Appointment data}    # in: towards the system
    - {actor: receptionist, direction: out, label: Calendar}           # out: from the system

diagrams:                               # optional saved diagram settings
  - id: uc-scheduling
    type: usecase
    module: M1
    positions: {UC-1.03: [640, 300]}    # manual position of one element, in drawing coordinates

team:                                   # optional
  - {name: Jane Doe, role: Business analyst}
```

Identifiers are free text: keep the convention the project already uses (FR-01, RF-01, REQ-12). Quote any value that contains a comma or a colon when using the `{...}` form.

## Validation codes

Errors (exit code 1): `missing-field`, `duplicate-id`, `invalid-value`, `unknown-actor`, `unknown-requirement`, `unknown-module`, `unknown-use-case`, `self-reference`, `include-cycle`, `generalization-cycle`.

Warnings (the model is probably incomplete):

| Code | Meaning | Usual fix |
|------|---------|-----------|
| `uncovered-requirement` | A functional requirement has no use case | Add the use case or link an existing one |
| `unused-actor` | An actor takes part in no use case | Link it or remove it |
| `orphan-use-case` | A use case has no actor and nothing includes it | Give it an actor or a relation |
| `untraced-use-case` | A use case names no requirement | Add `requirements` |
