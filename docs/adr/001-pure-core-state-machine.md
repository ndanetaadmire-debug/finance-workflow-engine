# ADR-001: Pure, synchronous core with an explicit state machine

**Status:** Accepted

**Context.** AP rules change often (new tolerance, new fraud check) and must be provably correct.

**Decision.** Validation, matching and reconciliation are pure functions. The workflow is a transition table, with an audit entry per transition. I/O (OCR, DB, HTTP) sits behind `Protocol` ports.

**Consequences.** Rules are trivial to unit test and review with finance. Adding a rule means adding a function to `DEFAULT_RULES`. Async I/O is introduced only at the edges.
