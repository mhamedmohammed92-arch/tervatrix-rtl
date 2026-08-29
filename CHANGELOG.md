# Changelog

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
- Byte-identical output with the `@tervatrix/rtl-ui` npm package, asserted by a
  parity test suite on both sides.
