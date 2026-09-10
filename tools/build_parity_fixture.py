"""Generate the cross-language parity fixture.

The two packages document each other as carrying the identical logic, so that
"a string prepared on either side of a project is byte-identical". That claim
needs a test on both sides of the same data, or it is only a sentence.

This script runs a corpus through BOTH implementations and refuses to write the
fixture unless they already agree, character for character. The fixture is then
committed to both repositories and asserted by each side's own test suite, so a
drift in either language fails a test rather than being absorbed by the next
regeneration.

    python tools/build_parity_fixture.py --rtl-ui ../rtl-ui

Regenerating is a deliberate act: if a case starts disagreeing, the fix belongs
in whichever implementation moved, not in the fixture.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

import tervatrix_rtl  # noqa: E402

# Built from codepoints, never written as literal or escaped characters in
# this file. An editor, a shell or a file round-trip silently folds U+2000
# into a plain space and drops U+000B and U+0085 altogether - the first two
# versions of this file did exactly that, and the corpus then agreed on every
# case for the boring reason that the cases probing the boundary no longer
# contained the characters at the boundary. chr() cannot be corrupted that
# way, and _assert_corpus_is_not_vacuous() below refuses to run if it ever is.
NBSP, VT, FF, CR = chr(0x00A0), chr(0x000B), chr(0x000C), chr(0x000D)
EN_QUAD, IDEO_SP = chr(0x2000), chr(0x3000)
THIN_SP, NEL, OGHAM = chr(0x2009), chr(0x0085), chr(0x1680)
LRI, PDI = chr(0x2066), chr(0x2069)
HE = "".join(map(chr, (0x05E9, 0x05DC, 0x05D5, 0x05DD)))   # shalom
AR = "".join(map(chr, (0x0645, 0x0631, 0x062D, 0x0628, 0x0627)))  # marhaba

# The boundary characters, by the name each case uses. If any of these stops
# being the codepoint it claims, the corpus is no longer testing what it says
# it tests, and a green run means nothing.
_BOUNDARY = {
    "nbsp": (NBSP, 0x00A0), "vtab": (VT, 0x000B), "formfeed": (FF, 0x000C),
    "cr": (CR, 0x000D), "en quad": (EN_QUAD, 0x2000),
    "ideographic": (IDEO_SP, 0x3000), "thin space": (THIN_SP, 0x2009),
    "next line": (NEL, 0x0085), "ogham": (OGHAM, 0x1680),
}


def _assert_corpus_is_not_vacuous() -> None:
    """Refuse to run unless every boundary character really is itself."""
    for label, (char, codepoint) in _BOUNDARY.items():
        if len(char) != 1 or ord(char) != codepoint:
            raise SystemExit(
                f"corpus is vacuous: {label} is {ascii(char)}, "
                f"expected U+{codepoint:04X}"
            )
        if not any(char in text for _, text, _ in CORPUS):
            raise SystemExit(f"corpus is vacuous: no case contains {label}")


# Every case is a shape that has actually broken something, or a boundary the
# two implementations could plausibly disagree on. Invisible characters are
# written as escapes so a reviewer can see what each case is.
CORPUS: list[tuple[str, str, str | None]] = [
    ("hours range", "שעות: 09:00-18:00", "he"),
    ("phone he", "דחוף: +972-4-000-0000", "he"),
    ("phone ar", "للطوارئ: +972-4-000-0000", "ar"),
    ("line starts with a digit", "2026 " + HE, "he"),
    ("url inside hebrew", HE + ": https://example.com/track/A-1042", "he"),
    ("email inside arabic", AR + ": a.b@example.com", "ar"),
    ("thousands separator", HE + " 1,250.00", "he"),
    ("hand-isolated value", HE + " " + LRI + "A-1042" + PDI + " " + HE, "he"),
    ("multiline", HE + "\n09:00-18:00\n" + HE, "he"),
    ("blank line between", HE + "\n\n09:00-18:00", "he"),
    ("trailing newline", HE + "\n", "he"),
    ("empty", "", "he"),
    ("only spaces", "   ", "he"),
    ("english left alone", "Thank you for your message", None),
    # The leading-whitespace boundary. Python's str.lstrip() strips every
    # Unicode space; the JavaScript class does not. That difference made the
    # two packages disagree on the last five of these until 2026-09-10.
    ("nbsp then hebrew", NBSP + HE, "he"),
    ("tab then hebrew", "\t" + HE, "he"),
    ("cr then hebrew", CR + HE, "he"),
    ("vtab then arabic", VT + AR, "ar"),
    ("formfeed then arabic", FF + AR, "ar"),
    ("en quad U+2000 then hebrew", EN_QUAD + HE, "he"),
    ("ideographic space U+3000 then hebrew", IDEO_SP + HE, "he"),
    ("thin space U+2009 then arabic", THIN_SP + AR, "ar"),
    ("next line U+0085 then hebrew", NEL + HE, "he"),
    ("ogham space U+1680 then hebrew", OGHAM + HE, "he"),
]

JS_DRIVER = """
import { prepareRtl, isolateLtrRuns, isolate, stripBidi } from %(pkg)s;
const cases = JSON.parse(process.argv[2]);
const out = cases.map(([name, text, lang]) => ({
  name,
  prepare: lang === null ? prepareRtl(text) : prepareRtl(text, lang),
  isolate_runs: isolateLtrRuns(text),
  strip: stripBidi(lang === null ? prepareRtl(text) : prepareRtl(text, lang)),
}));
process.stdout.write(JSON.stringify(out));
"""


def js_results(rtl_ui: pathlib.Path) -> list[dict]:
    entry = (rtl_ui / "src" / "index.js").resolve()
    if not entry.exists():
        raise SystemExit(f"rtl-ui entry point not found: {entry}")
    driver = JS_DRIVER % {"pkg": json.dumps(entry.as_uri())}
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "driver.mjs"
        path.write_text(driver, encoding="utf-8")
        proc = subprocess.run(
            [
                "node",
                str(path),
                json.dumps([[n, t, l] for n, t, l in CORPUS], ensure_ascii=True),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if proc.returncode != 0:
        raise SystemExit(f"node driver failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def py_results() -> list[dict]:
    out = []
    for name, text, lang in CORPUS:
        prepared = (
            tervatrix_rtl.prepare_outbound(text)
            if lang is None
            else tervatrix_rtl.prepare_outbound(text, lang)
        )
        out.append(
            {
                "name": name,
                "prepare": prepared,
                "isolate_runs": tervatrix_rtl.isolate_ltr_runs(text),
                "strip": tervatrix_rtl.strip_bidi(prepared),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl-ui", required=True, type=pathlib.Path,
                    help="path to a checkout of the rtl-ui repository")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "tests" / "parity_fixture.json")
    args = ap.parse_args()
    _assert_corpus_is_not_vacuous()

    js = js_results(args.rtl_ui)
    py = py_results()

    disagreements = []
    for j, p, (name, text, lang) in zip(js, py, CORPUS):
        for field in ("prepare", "isolate_runs", "strip"):
            if j[field] != p[field]:
                disagreements.append((name, field, j[field], p[field]))

    if disagreements:
        print(f"REFUSING to write the fixture - {len(disagreements)} disagreement(s):\n")
        for name, field, a, b in disagreements:
            print(f"  {name} / {field}")
            print(f"    rtl-ui        {ascii(a)}")
            print(f"    tervatrix-rtl {ascii(b)}")
        print("\nFix the implementation that moved. The fixture records agreement;")
        print("it is not a place to record a difference.")
        return 1

    fixture = {
        "_comment": (
            "Cross-language parity fixture. Generated by "
            "tools/build_parity_fixture.py only when tervatrix-rtl (Python) and "
            "tervatrix-rtl-ui (JavaScript) already agree character for "
            "character. Committed to BOTH repositories and asserted by both "
            "test suites, so a drift in either language fails a test instead of "
            "being absorbed the next time this file is regenerated."
        ),
        "cases": [
            {"name": n, "input": t, "language": l, **{k: j[k] for k in
             ("prepare", "isolate_runs", "strip")}}
            for (n, t, l), j in zip(CORPUS, js)
        ],
    }
    args.out.write_text(
        json.dumps(fixture, ensure_ascii=True, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(CORPUS)} cases agree - wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
