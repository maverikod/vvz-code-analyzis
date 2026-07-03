"""
Local merge and cherry-pick operations act on the working tree and history
of the resolved project repository. They are never gated by the
protected-branch restriction. Their only route to a remote is a separate,
separately-restricted push operation. This module fixes which git operations
the protected-branch restriction governs; it does not itself implement the
push guard. The push guard enforcement mechanism lives in a different module,
not created here.
"""

# Git operation names governed by the protected-branch restriction. Currently
# this contains only "push", because push is the only remote-publication route
# the restriction governs.
PROTECTED_BRANCH_GATE_APPLIES_TO: frozenset[str] = frozenset({"push"})

# Local operation names explicitly exempt from the protected-branch restriction,
# because they act only on the local working tree and history and never
# themselves reach a remote.
LOCAL_OPERATIONS_EXEMPT_FROM_PROTECTED_GATE: frozenset[str] = frozenset({"merge", "cherry_pick"})


def is_protected_branch_gate_applicable(operation: str) -> bool:
    """Return whether the protected-branch restriction governs an operation.

    The result is True only for operations the protected-branch restriction
    governs, currently only "push". It returns False for every other operation
    name, including "merge", "cherry_pick", and any name not present in
    PROTECTED_BRANCH_GATE_APPLIES_TO. Local merge and cherry-pick are never
    gated by this restriction because their only route to a remote is a
    separate, separately-restricted push operation. The push guard enforcement
    itself is implemented elsewhere, not in this module.

    Args:
        operation: Git operation name.

    Returns:
        True when the protected-branch gate applies to the operation.
    """
    return operation in PROTECTED_BRANCH_GATE_APPLIES_TO
