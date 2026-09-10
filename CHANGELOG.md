# Changelog

## 1.0.1 (unreleased)

A correctness fix in `force_rtl_paragraphs()`, and the parity claim turned into
a check.

- `force_rtl_paragraphs()` now looks past exactly the same leading-whitespace
  class as the JavaScript package - space, tab, U+000B, U+000C, U+000D and
  U+00A0 - instead of `str.lstrip()`, which strips every Unicode space there is.
  The two packages therefore disagreed whenever a line began with U+2000,
  U+3000, U+2009, U+0085 or U+1680: this side looked past the space and saw a
  Hebrew letter, the other side did not and added an RTL mark. Measured
  2026-09-10 on 27 inputs, 5 of them divergent. Rendering was unaffected in all
  five, but the documented promise that a string prepared on either side is
  byte-identical was not true.
- `tests/parity_fixture.json` + `tests/test_parity.py` - parity is now asserted
  against output generated from the JavaScript implementation itself. The old
  `ParityWithJavaScriptTest` kept its expectations by hand and was green
  throughout the divergence above; it stays as readable documentation of the
  contract, with the generated suite enforcing it.
- Corrected the npm package name throughout: it is `tervatrix-rtl-ui`, not
  `@tervatrix/rtl-ui`. The scoped name was never published and never will be,
  so every link and mention of it - including the one on this package's own
  PyPI page - pointed at a 404.

## 1.0.0

First public release. Extracted from a WhatsApp agent running in production.

- `prepare_outbound()` — LTR isolates for numbers, URLs, e-mail addresses and
  time ranges, plus the RLM line-start fix. LTR languages returned untouched.
- `isolate_ltr_runs()`, `force_rtl_paragraphs()` — the two halves, callable on
  their own. Both idempotent.
- `isolate()`, `format_time_range()` — wrap a value the pattern is deliberately
  too strict to catch.
- `detect_language()`, `is_rtl()`, `dir_for()` — `is_rtl` accepts full locale
  tags (`he-IL`, `ar_EG`) as well as bare subtags, and covers `fa` and `ur`.
  `detect_language()` scores the prose only: URLs, e-mail addresses and phone
  numbers are removed first, so a Hebrew message that merely contains a link is
  still read as Hebrew rather than flipped to English.
- The number pattern treats a thousands separator as part of the run, so
  `1,250.00` isolates as one value instead of splitting at the comma.
- `strip_bidi()` — the exact inverse, for equality checks and stored values.
- Byte-identical output with the `tervatrix-rtl-ui` npm package, asserted by a
  parity test suite on both sides.
