# Use case guidelines

Notation follows UML 2.5.1 (use case diagrams) and the goal-oriented writing style of Cockburn's "Writing Effective Use Cases".

## Finding actors and use cases

- Start from the requirements: each functional requirement names who needs it. That role is an actor.
- An actor is outside the system. A person is `kind: human`; another system is `kind: system`.
- `type: primary` starts use cases to get value. `type: secondary` takes part in a use case someone else starts. `type: external` is a system the product talks to.
- A stakeholder who never touches the system (a sponsor, a manager who only receives reports by other means) is not an actor.
- Ask "what does this actor want to achieve?" Each answer is a candidate use case.

## Naming and granularity

- Name: verb in the infinitive plus object, from the actor's point of view: "Book appointment", "Approve invoice".
- One goal per use case. "Manage products and suppliers" is two goals: split it into "Manage products" and "Manage suppliers".
- Not a use case: a screen, a button, a validation step, a field. Those are steps of a flow.
- A good size finishes in one sitting of the actor and leaves the business in a consistent state.
- Maintenance sets (create, modify, deactivate) can be one parent "Manage X" with the three as `specializes`, or three separate use cases. Pick one style for the whole model.

## Relations

| Relation | Meaning | Direction of the arrow | Model field |
|----------|---------|------------------------|-------------|
| «include» | The base always runs the included behaviour | base to included | `includes` on the base |
| «extend» | Optional behaviour under a condition | extension to base | `extends` on the extension, with `condition` |
| Generalization | The child is a kind of the parent | child to parent | `specializes` on the child |

- Use «include» when two or more use cases share a step sequence, or to keep one rule in one place (for example every state change goes through one included use case).
- An included use case with no actor of its own is fine: it is reached through its base.
- A specialised use case inherits the actors of its parent; the diagram does not repeat them.
- Relations never express sequence. "First A, then B" belongs in a flow or in an activity diagram.

## Writing the card

- `purpose`: one sentence, why the actor does it.
- `preconditions`: states that are true before, not actions ("The user is signed in").
- `postconditions`: observable results after success ("The appointment is stored with status Booked").
- `main_flow`: the success path. Alternate actor and system steps; one action per step; the system validates before it stores.
- `alternative_flows`: other valid paths, labelled with the step they leave from ("3a. ... continues at step 4").
- `exceptions`: failures, labelled the same way, each saying what the system does and where the flow resumes or ends.
- Reference other use cases by id where a step runs them ("... sends the confirmation (UC-1.05)").
- When the business has not decided something, write the assumption and label it as an assumption of the team.

## Review checklist

1. `sedocs check` shows 0 errors; every warning is fixed or explained.
2. Every use case name is verb plus object and holds one goal.
3. Every «extend» has a condition; no relation is used to show order.
4. Each card's steps match the relations: an included use case appears as a step of its base.
5. Business rules that restrict a flow appear in an exception or a precondition of some use case.
6. The diagram has no line crossing a use case and no more than about 12 use cases.
7. Terms are the same in the requirement tables, the cards and the diagrams.
