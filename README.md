# tervatrix-rtl

Correct right-to-left text for Hebrew and Arabic, in one dependency-free
module. Pure standard library, Python 3.9+, MIT.

It fixes the four bidi bugs that ship in almost every RTL application and are
invisible in review, because they only appear once real data lands in the
layout:

| what the user sees | why | the fix |
|---|---|---|
| `+972-4-000-0000` renders as `0000-000-4-972+` | the dashes are *neutral* characters and inherit the paragraph's RTL direction | `prepare_outbound()` wraps it in a left-to-right isolate |
| opening hours `09:00-18:00` render as `18:00-09:00`, closing time first | two number runs with a neutral between them get reordered as a unit | the pattern treats a time range as **one** run |
| a whole Hebrew line flips to left-aligned because it starts with `2026` or `WhatsApp` | the first-strong-character rule guesses the paragraph direction | an invisible right-to-left mark is prefixed to the line |
| a prepared string no longer equals the string it came from | the marks are invisible but real characters | `strip_bidi()`, the exact inverse |

Extracted from a WhatsApp agent answering Hebrew, Arabic and English customers
in production.

---

## Install

```bash
pip install tervatrix-rtl
```

No dependencies. Nothing to configure.

---

## The 30-second version

```python
from tervatrix_rtl import prepare_outbound

message = "שעות פתיחה: 09:00-18:00\nלשאלות: +972-4-000-0000"

send(prepare_outbound(message, "he"))
```

That one call wraps the time range and the phone number in left-to-right
isolates and marks the line that starts with a digit. An English string is
returned **byte for byte untouched**, so English never carries invisible control
characters into your logs, your tests or your database.

---

## API

### `prepare_outbound(text, language=None)`

The single call to make on any string before you render or send it. Runs
`isolate_ltr_runs` then `force_rtl_paragraphs`. Returns LTR languages unchanged.

Omit `language` and it is detected from the script the text is written in.

### `isolate_ltr_runs(text)`

Wraps URLs, `www.` hosts, e-mail addresses, phone numbers, prices and time
ranges in `U+2066 … U+2069`.

Idempotent, and **composable**: it processes only what lies outside any isolate
that is already there. So you can wrap one value by hand with `isolate()`, drop
it into a sentence, and still pass the whole sentence through
`prepare_outbound()` — the hand-wrapped value survives untouched and everything
around it is still protected.

### `force_rtl_paragraphs(text)`

Prefixes `U+200F` to every line that does not already begin with a strong RTL
character. Applied line by line, which is why an isolate is never allowed to
cross a newline — a pair split over two lines would never balance.

### `isolate(value)`

Wraps one value unconditionally. Use it when you already know what the value is
and the pattern is deliberately too strict to catch it — a bare order id like
`A7`, a two-digit table number.

```python
f"הזמנה {isolate(order.id)} מוכנה"
```

### `format_time_range(start, end, separator="-")`

`format_time_range("09:00", "18:00")` gives an isolated `09:00-18:00` that
cannot be reordered.

### `detect_language(text)` → `'he' | 'ar' | 'en'`

Counts characters per script rather than stopping at the first hit, so one Latin
brand name inside a Hebrew sentence does not switch the whole string to English.
URLs, e-mail addresses and phone numbers are removed before counting - they are
not evidence of a language, and a single link otherwise carries enough Latin
letters to flip a short Hebrew message to English.
Falls back to `'en'` for digits-only, emoji-only and empty input.

### `is_rtl(language)` and `dir_for(language)`

`is_rtl` accepts a bare subtag or a full tag: `he`, `he-IL`, `ar_EG`, `fa-IR`,
`ur`. `dir_for` returns `'rtl'` or `'ltr'`, ready to drop into an HTML `dir`
attribute.

### `strip_bidi(text)`

Removes every bidi control character, including the legacy embedding marks
(`U+202A`–`U+202E`) found in old translation files.

**Call this before comparing strings.** The marks are invisible, so an
unstripped string fails an equality check for no visible reason — in a test
assertion, a database `WHERE`, a de-duplication key. `strip_bidi(prepare_outbound(x))`
is exactly `x`.

### `LRI`, `PDI`, `RLM`, `RTL_LANGUAGES`

The control characters (`U+2066`, `U+2069`, `U+200F`) and the tuple of RTL
primary subtags, exported so you can assert on them in your own tests.

---

## Where it belongs in a web app

Do the isolating **once, on the way out**, not scattered through templates:

```python
# FastAPI / Flask / Django - one place, at the edge
from tervatrix_rtl import dir_for, prepare_outbound

@app.get("/order/{order_id}")
def order_page(order_id: str, lang: str = "he"):
    order = repo.get(order_id)
    return render(
        "order.html",
        dir=dir_for(lang),
        lang=lang,
        summary=prepare_outbound(order.summary, lang),
    )
```

And strip on the way **in**, before anything is compared or stored:

```python
from tervatrix_rtl import strip_bidi

clean = strip_bidi(request.form["name"]).strip()
```

That second line matters more than it looks. Text pasted from a chat app,
a PDF or a spreadsheet routinely carries `U+200F` and `U+202A`–`U+202E`.
Stored unstripped, the row never matches on lookup and the bug is invisible in
every log and every database client.

---

## Tests

No framework to install; `unittest` ships with Python.

```bash
python -m unittest discover -s tests -t .
```

They cover language detection, isolate placement, idempotency,
isolate/newline balance, and the round trip through `strip_bidi`.

Parity with the JavaScript package is enforced rather than described.
`tests/parity_fixture.json` is generated by running **both** implementations
over the same corpus; the generator refuses to write it while they disagree on
any case, so the fixture can only ever record agreement. Both repositories
commit that file and assert against it, which means a drift in either language
fails a test instead of being absorbed the next time it is regenerated.

```bash
python tools/build_parity_fixture.py --rtl-ui ../rtl-ui   # regenerate, deliberately
```

---

## Licence

MIT — see [LICENSE](LICENSE). Use it commercially, fork it, ship it. No
warranty.

---

## Where this came from

This package is the RTL layer of a WhatsApp agent that answers Hebrew, Arabic
and English customers on the official Meta Cloud API. Two more pieces of it are
public and free:

- **[`tervatrix-rtl-ui`](https://www.npmjs.com/package/tervatrix-rtl-ui)** —
  the identical logic in JavaScript, plus logical-property CSS utilities and an
  optional React wrapper. Same function names, same behaviour, so a string
  prepared on either side of a project is byte-identical.
- **[`wa-agent-starter`](https://github.com/mhamedmohammed92-arch/wa-agent-starter)**
  — a complete, working WhatsApp agent in FastAPI: Meta webhook, HMAC signature
  verification, language detection, keyword FAQ, this RTL handling, and 50
  passing tests. MIT, self-hosted, no account with us.

If you need more than a keyword bot, **wa-agent-kit** is the paid version. It
adds a Qdrant knowledge base so the agent answers questions nobody wrote a
keyword for, multi-tenant support for many business numbers on one deployment,
human handover, an admin panel, an AI-provider abstraction, and 12 months of
updates.

→ **[Get wa-agent-kit](https://github.com/mhamedmohammed92-arch/wa-agent-starter#what-the-paid-kit-adds)**
