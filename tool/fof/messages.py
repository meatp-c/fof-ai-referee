"""Output vocabulary of the engine in one place: prefixes of the output lines and the rule citation format.

Everything the AI or the player reads starts with one of these words, so the referee briefing (AI_BRIEFING.md)
can refer to them and a different output language only has to change this module.
"""

ALLOWED = "ALLOWED"  # an order or action passed every check and was booked
VIOLATION = "VIOLATION"  # refused, nothing saved
BOARD = "Board"  # a marker or counter to place, flip or remove on the physical board
NOTE = "Note"  # non-binding hint
CHECKSTAMP = "CHECKSTAMP"  # consistency line that closes every command
RULE = "RULE"  # citation word inside square brackets


def rule(ref, page=None):
    """Rule citation: rule("6.1.2", 44) -> '[RULE 6.1.2 p.44]', rule("CSR 7 p.15") -> '[CSR 7 p.15]' (already complete)."""
    if page is not None:
        return f"[{RULE} {ref} p.{page}]"
    if ref.startswith("[") or " " in ref and not ref[0].isdigit():
        return ref if ref.startswith("[") else f"[{ref}]"
    return f"[{RULE} {ref}]"
