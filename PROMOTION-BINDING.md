# Forward evidence binding

Promotion requires forward evidence naming the exact strategy and version,
the validation protocol hash and validation result hash, and a 64-character
lowercase hexadecimal forward result hash. The independently reviewed comparison
must name that same forward result hash. Missing or mismatched bindings fail closed.

Inside the promotion transaction, supplied validation evidence must also equal
the latest recorded validation evidence for that strategy/version. Superseded
receipts cannot authorize promotion. Champion swaps and rollback retain these gates.

These are consistency checks on reviewer attestations, not cryptographic proof
of market results or external receipt authenticity. Existing independent review,
forward sample, net expectancy and risk gates remain required. No live execution
is enabled. Legacy generic forward payloads must acquire explicit reviewed bindings;
there is no automatic migration or actual strategy promotion.

Deterministic regression tests cover missing/wrong identity and hashes, mismatched
comparison receipts, superseded candidate evidence, unchanged state/journal on
rejection, and bound successful promotion, champion swap and rollback.
