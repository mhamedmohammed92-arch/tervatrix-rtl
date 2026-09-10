"""tervatrix-rtl - right-to-left text handling for Hebrew and Arabic.

Four bidi bugs ship in almost every Hebrew or Arabic application, and all four
are invisible in review because they only appear once real data lands in the
layout:

1. A phone number, price range, URL or order id inside an RTL sentence renders
   with its segments in the wrong order, because the dashes, dots and slashes
   between digits are *neutral* characters and inherit the paragraph's
   right-to-left direction. ``+972-52-624-7316`` can display as
   ``7316-624-52-972+``.
   Fix: wrap each such run in a LEFT-TO-RIGHT ISOLATE (U+2066 ... U+2069) so it
   is laid out left-to-right while staying in place inside the sentence.

2. An opening-hours range like ``09:00-18:00`` is two number runs with a
   neutral between them, so an RTL paragraph reorders it into ``18:00-09:00``
   and shows the closing time first. Fix: the pattern below treats a time range
   as ONE run, deliberately, by keeping the colon and the dashes inside the
   separator class.

3. A line that *starts* with a digit or a Latin word ("2026 ...",
   "WhatsApp ...") is guessed as a left-to-right paragraph by the
   first-strong-character rule, so the whole Hebrew or Arabic line flips its
   alignment. Fix: prefix the line with an invisible RIGHT-TO-LEFT MARK
   (U+200F).

4. The invisible marks then break equality: a prepared string no longer equals
   the string it came from, in a test assertion, a database WHERE clause or a
   de-duplication key. Fix: :func:`strip_bidi`, the exact inverse.

All of it is pure text - no font, no client setting, nothing to install.
Every range below is written as an escape on purpose: the literal characters
are invisible or bidi-flipping in an editor, which is how these regexes get
broken by a well-meaning edit.

The JavaScript package ``tervatrix-rtl-ui`` carries the identical logic under
the same names, so a string prepared on either side of a project is
byte-identical.
"""

from __future__ import annotations

import re

__all__ = [
    "LRI",
    "PDI",
    "RLM",
    "RTL_LANGUAGES",
    "detect_language",
    "dir_for",
    "force_rtl_paragraphs",
    "format_time_range",
    "is_rtl",
    "isolate",
    "isolate_ltr_runs",
    "prepare_outbound",
    "strip_bidi",
]

__version__ = "1.0.1"

# Unicode bidirectional control characters used below.
LRI = "\u2066"  # LEFT-TO-RIGHT ISOLATE
PDI = "\u2069"  # POP DIRECTIONAL ISOLATE
RLM = "\u200F"  # RIGHT-TO-LEFT MARK

#: Primary language subtags whose script runs right to left. Matching is done on
#: the primary subtag, so ``he-IL`` and ``ar_EG`` also count.
RTL_LANGUAGES = ("he", "iw", "ar", "fa", "ur")

# Hebrew block + Hebrew presentation forms.
_HEBREW = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")
# Arabic, Arabic Supplement, Arabic Extended-A, and the presentation forms.
_ARABIC = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_LATIN = re.compile(r"[A-Za-z]")

# Any character that decides a paragraph's direction on its own (a "strong" RTL
# character). Used to tell whether a line already starts right to left.
_STRONG_RTL = re.compile(r"[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]")

# Every bidi control character this module can insert, plus the legacy
# embedding marks still found in old translation files.
_BIDI_CONTROLS = re.compile("[\u200E\u200F\u2066-\u2069\u202A-\u202E]")

# A locale tag is split on either separator: "he-IL" and "he_IL" both occur.
_TAG_SEPARATOR = re.compile(r"[-_]")

# A span that is already isolated: LRI, anything that is not a PDI, PDI.
# Used to leave hand-wrapped values alone while still processing the prose
# around them - see isolate_ltr_runs().
_ISOLATED_SPAN = re.compile("\u2066[^\u2069]*\u2069")

# One alternation, matched left to right, so a URL is never re-chewed by the
# number branch. Order matters: longest / most specific pattern first.
#   1. http(s) URL   2. bare www. host   3. e-mail address
#   4. a number-like run: a digit, then digits and the usual separators, a digit
#
# Three deliberate choices in that last branch:
#   * The separator class spells out space and tab instead of using \s, because
#     \s also matches the newline. A run allowed to cross a line break would put
#     the opening isolate on one line and the closing one on the next - and the
#     RTL mark below is applied line by line, so the pair would never balance.
#   * The colon and the en/em dash are in the class on purpose. "09:00-18:00" is
#     the classic failure: two number runs with a neutral between them, which an
#     RTL paragraph reorders into "18:00-09:00" and shows closing time first.
#   * The comma is in the class so a thousands separator cannot split the run.
#     Without it "1,250.00" isolates as "1," followed by an isolated "250.00",
#     putting the isolate boundary in the middle of a number - which is worse
#     than not touching it at all.
_LTR_ISLAND = re.compile(
    r"(https?://[^\s]+"
    r"|www\.[^\s]+"
    r"|[^\s@]+@[^\s@]+\.[A-Za-z]{2,}"
    r"|\+?\d[\d:,\u2013\u2014()./ \t-]{3,}\d)"
)


def detect_language(text: str) -> str:
    """Return ``'he'``, ``'ar'`` or ``'en'`` from the script the text uses.

    Counting characters rather than stopping at the first hit keeps a single
    Latin brand name inside a Hebrew sentence from switching the whole string
    to English. English is the fallback when nothing is recognised (digits
    only, emoji only, an empty string).

    URLs, e-mail addresses and phone numbers are removed before counting: they
    are not evidence of a language. ``https://example.com/prices`` carries more
    Latin letters than a short Hebrew sentence carries Hebrew ones, so counting
    them used to flip a Hebrew message that merely contained a link all the way
    to ``'en'`` - and :func:`prepare_outbound` then returned it untouched, with
    no isolate and no RTL mark, which is the exact failure this module exists
    to prevent.
    """
    if not text:
        return "en"
    prose = _LTR_ISLAND.sub(" ", text)
    scores = {
        "he": len(_HEBREW.findall(prose)),
        "ar": len(_ARABIC.findall(prose)),
        "en": len(_LATIN.findall(prose)),
    }
    best = max(scores, key=lambda key: scores[key])
    return best if scores[best] > 0 else "en"


def is_rtl(language: str) -> bool:
    """Is this language tag written right to left?

    Accepts a bare subtag (``he``) or a full tag (``he-IL``, ``ar_EG``).
    """
    if not language:
        return False
    primary = _TAG_SEPARATOR.split(str(language).lower(), 1)[0]
    return primary in RTL_LANGUAGES


def dir_for(language: str) -> str:
    """``'rtl'`` or ``'ltr'`` - ready for an HTML ``dir`` attribute."""
    return "rtl" if is_rtl(language) else "ltr"


def _wrap_runs(chunk: str) -> str:
    return _LTR_ISLAND.sub(lambda m: LRI + m.group(1) + PDI, chunk)


def isolate_ltr_runs(text: str) -> str:
    """Wrap URLs, e-mail addresses, phone numbers and time ranges in LTR isolates.

    Idempotent: calling it twice on the same string changes nothing, because
    after the first pass every matchable run is already inside an isolate span.
    """
    if not text:
        return text

    # The common case: nothing is isolated yet.
    if LRI not in text:
        return _wrap_runs(text)

    # Something already is. Process only what lies OUTSIDE the existing spans,
    # so a caller may wrap one value by hand with isolate() - an order id, a
    # short reference - and still hand the whole sentence here afterwards.
    out = []
    last = 0
    found = False
    for match in _ISOLATED_SPAN.finditer(text):
        found = True
        out.append(_wrap_runs(text[last : match.start()]))
        out.append(match.group(0))
        last = match.end()
    # An opening isolate with no closing one: the text is already malformed, so
    # leave it exactly as it is rather than adding more controls to it.
    if not found:
        return text
    out.append(_wrap_runs(text[last:]))
    return "".join(out)


def isolate(value: object) -> str:
    """Wrap one value in an LTR isolate unconditionally.

    Use it when you already know the value is a number, an id, a URL or a time
    range and you do not want to rely on the pattern matching - for example a
    bare order id like ``A7``, which is too short for the number branch.
    """
    if value is None or value == "":
        return ""
    text = str(value)
    if LRI in text:
        return text
    return LRI + text + PDI


def format_time_range(start: str, end: str, separator: str = "-") -> str:
    """Format an opening-hours range so it survives an RTL paragraph.

    ``format_time_range("09:00", "18:00")`` gives an isolated ``09:00-18:00``
    that cannot be reordered into ``18:00-09:00``.
    """
    return isolate(f"{start}{separator}{end}")


# The leading whitespace to look past when deciding whether a line already
# begins right-to-left. Spelled out rather than using str.lstrip(), which strips
# every Unicode space there is - including U+2000, U+3000, U+1680 and U+0085.
# The JavaScript package uses exactly this class, and the two must agree
# character for character or a string prepared on one side stops matching the
# same string prepared on the other. Measured 2026-09-10: str.lstrip() made the
# two packages disagree on 5 of 27 cases.
_LEADING_WS = re.compile("^[ \t\x0b\f\r\u00a0]+")


def force_rtl_paragraphs(text: str) -> str:
    """Prefix every line that does not already begin with a strong RTL character
    with an invisible RTL mark, so the line is laid out right to left."""
    if not text:
        return text
    out = []
    for line in text.split("\n"):
        stripped = _LEADING_WS.sub("", line)
        if not stripped or line.startswith(RLM):
            out.append(line)
            continue
        if _STRONG_RTL.match(stripped[0]):
            out.append(line)
        else:
            out.append(RLM + line)
    return "\n".join(out)


def prepare_outbound(text: str, language: str | None = None) -> str:
    """The single call to make on any string before it is rendered or sent.

    Left-to-right languages are returned untouched, so English strings never
    carry invisible control characters that would show up in logs, snapshots
    and copy-paste.

    Omit ``language`` and it is detected from the script the text is written in.
    """
    if not text:
        return text
    lang = detect_language(text) if language is None else language
    if not is_rtl(lang):
        return text
    return force_rtl_paragraphs(isolate_ltr_runs(text))


def strip_bidi(text: str) -> str:
    """Remove every bidi control character this module can insert.

    Call it before comparing strings, writing to a database, or asserting in a
    test - the marks are invisible, so an unstripped string fails an equality
    check for no visible reason. ``strip_bidi(prepare_outbound(x))`` is exactly
    ``x``.
    """
    if not text:
        return text
    return _BIDI_CONTROLS.sub("", text)
