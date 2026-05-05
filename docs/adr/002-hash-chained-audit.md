# ADR-002: Hash-chained, append-only audit log

**Status:** Accepted

**Context.** Auditors need to trust that approval history was not edited after the fact.

**Decision.** Each audit entry stores `prev_hash` and `hash = sha256(canonical_json(entry))`. Postgres permissions make the table insert-only for the app role.

**Consequences.** Any modification breaks `verify()`. Periodically anchoring the latest hash externally (e.g. in a signed daily report) extends this to protect against a DBA rewriting the whole chain.
