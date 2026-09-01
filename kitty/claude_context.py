"""
Python half of the Claude Code context breakdown filter. See kitty/claude-context.h for what
the feature is and what removing it involves.

Its only job is to carry the orchestrator layer's token count from the user variable the
session launcher sets down into the Screen field the C filter reads, so that filter never has
to take the GIL to look inside a Python dict on a per-row path.
"""

from typing import Any

# Set by the `ai` launcher in the .linux-config repo, which must use this exact name and unit.
# Unrounded tokens on purpose: the filter subtracts this from a figure Claude Code prints, and
# a count rounded to thousands would put all of that rounding into the small remainder.
CLAUDE_ORCH_TOKENS_VAR = 'claude_orch_tokens_raw'
CLAUDE_ORCH_TOKENS_MAX = 0xffffffff


def parse_claude_orch_tokens(val: str) -> int:
    """
    Reads the user variable's value, treating anything unexpected as "no filter for this
    window" rather than guessing, since the result is subtracted from real output.
    """
    try:
        ans = int(val.strip())
    except ValueError:
        return 0
    return ans if 0 < ans <= CLAUDE_ORCH_TOKENS_MAX else 0


def mirror_orch_tokens(screen: Any, key: str, val: str | None) -> None:
    """
    Mirrors one user variable assignment into the Screen field. A cleared or absent value
    disables the filter for the window, so a reused window cannot inherit a stale count.
    """
    if key != CLAUDE_ORCH_TOKENS_VAR:
        return
    screen.claude_orch_tokens = parse_claude_orch_tokens(val) if val is not None else 0
