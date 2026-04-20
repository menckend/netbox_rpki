"""
Subsystem maturity metadata for the netbox_rpki plugin.

Each navigation group (subsystem) is assigned a maturity level that conveys
its stability posture to operators. Maturity levels are surfaced in navigation
labels, documented in the Sphinx site, and consumed by the ``hide_experimental``
plugin setting.

Maturity level definitions
--------------------------

GA
    Generally available. The subsystem has shipped, is covered by the contract
    test suite, and its data model and public API surface are considered stable
    for the current release line.

Beta
    Feature-complete and tested but still settling. The subsystem is expected to
    evolve across minor releases. Breaking changes are possible but will be
    documented in the changelog.

Experimental
    Early-stage or recently introduced. The subsystem may change significantly,
    be restructured, or be removed. Use cautiously in production.
"""

from enum import Enum


class MaturityLevel(Enum):
    """Subsystem maturity classification."""

    GA = "GA"
    BETA = "Beta"
    EXPERIMENTAL = "Experimental"


#: Maps navigation group names to their maturity levels.
#:
#: Groups not listed here default to ``MaturityLevel.GA``.
SUBSYSTEM_MATURITY: dict[str, MaturityLevel] = {
    # --- GA subsystems ---
    "Resources": MaturityLevel.GA,
    "ROAs": MaturityLevel.GA,
    "Objects": MaturityLevel.GA,
    "Trust": MaturityLevel.GA,
    "Validation": MaturityLevel.GA,
    # --- Beta subsystems ---
    "Intent": MaturityLevel.BETA,
    "Derivation": MaturityLevel.BETA,
    "Reconciliation": MaturityLevel.BETA,
    "Provider": MaturityLevel.BETA,
    "Imported": MaturityLevel.BETA,
    # --- Experimental subsystems ---
    "IRR": MaturityLevel.EXPERIMENTAL,
    "Linting": MaturityLevel.EXPERIMENTAL,
    "Delegated": MaturityLevel.EXPERIMENTAL,
    "Governance": MaturityLevel.EXPERIMENTAL,
    "Lifecycle": MaturityLevel.EXPERIMENTAL,
}

#: Short badge text appended to navigation labels for non-GA subsystems.
MATURITY_BADGE_TEXT: dict[MaturityLevel, str] = {
    MaturityLevel.BETA: "\u2009\u03b2",        # thin-space + Greek beta
    MaturityLevel.EXPERIMENTAL: "\u2009\u26a0",  # thin-space + warning sign
}


def get_maturity(group_name: str) -> MaturityLevel:
    """Return the maturity level for a navigation group, defaulting to GA."""
    return SUBSYSTEM_MATURITY.get(group_name, MaturityLevel.GA)


def get_badge(group_name: str) -> str:
    """Return the badge suffix for *group_name*, or empty string for GA."""
    return MATURITY_BADGE_TEXT.get(get_maturity(group_name), "")


def is_hidden(group_name: str, *, hide_experimental: bool) -> bool:
    """Return True when *group_name* should be suppressed from navigation."""
    if hide_experimental and get_maturity(group_name) is MaturityLevel.EXPERIMENTAL:
        return True
    return False
