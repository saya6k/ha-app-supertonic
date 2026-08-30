"""SSML handling for the Supertonic bridge.

Wyoming 1.10.0 added `text_format` ("text" | "ssml" | anything else) to
`Synthesize` / `SynthesizeStart`, but gave servers no way to *decline* it:
`TtsProgram` has no SSML capability flag, so a client may send SSML
unilaterally and the reference HTTP server just passes the field through.

Supertonic has no SSML support, so the choice is between speaking the raw
markup ("speak version equals one point zero…") and degrading to the text it
wraps. We degrade: tags are dropped, entities are unescaped. Prosody hints
(`<break>`, `<emphasis>`, `<sub alias=...>`) are lost rather than honoured —
losing a pause beats reading tag soup aloud.

No XML parser: SSML arrives as an unvalidated string, may be a fragment, and
in the streaming path is split across chunks at arbitrary byte boundaries.
We only ever want the character data, so tag-stripping is both sufficient
and total — it cannot raise on malformed input.
"""

from __future__ import annotations

import html
import re
from typing import Tuple

# A complete tag: "<" ... ">" with no intervening ">".
_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")


def strip_ssml(text: str) -> str:
    """Reduce SSML markup to the text it wraps.

    Tags become a single space so `a<break/>b` does not weld into `ab`;
    runs of whitespace are then collapsed.
    """
    return _WHITESPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def split_partial_tag(text: str) -> Tuple[str, str]:
    """Split off a trailing incomplete tag.

    In the streaming path a tag can straddle a chunk boundary — chunk 1 ends
    `...Hello <emph`, chunk 2 opens `asis>world...`. Stripping each chunk
    independently would leave `asis>world` in the spoken text, so the tail
    from an unclosed "<" is held back and prepended to the next chunk.

    Returns (safe_to_strip, carry).
    """
    idx = text.rfind("<")
    if idx == -1 or ">" in text[idx:]:
        return text, ""

    return text[:idx], text[idx:]
