"""Language detection, LTR isolates, the RLM line-start fix, and the round trip.

Run them with the standard library alone:

    python -m unittest discover -s tests -t .
"""

import unittest

from tervatrix_rtl import (
    LRI,
    PDI,
    RLM,
    RTL_LANGUAGES,
    detect_language,
    dir_for,
    force_rtl_paragraphs,
    format_time_range,
    is_rtl,
    isolate,
    isolate_ltr_runs,
    prepare_outbound,
    strip_bidi,
)

# Written as escapes on purpose. Literal RTL words reorder the surrounding
# source line in an editor, which is exactly how tests like these get silently
# broken by an unrelated edit.
HEBREW = "שלום"          # shalom
ARABIC = "مرحبا"    # marhaba


class ControlCharacterTest(unittest.TestCase):
    def test_code_points_are_the_documented_ones(self):
        self.assertEqual(ord(LRI), 0x2066, "LRI must be LEFT-TO-RIGHT ISOLATE")
        self.assertEqual(ord(PDI), 0x2069, "PDI must be POP DIRECTIONAL ISOLATE")
        self.assertEqual(ord(RLM), 0x200F, "RLM must be RIGHT-TO-LEFT MARK")

    def test_rtl_languages_is_immutable(self):
        self.assertIsInstance(RTL_LANGUAGES, tuple)


class DetectLanguageTest(unittest.TestCase):
    def test_hebrew(self):
        self.assertEqual(detect_language(HEBREW), "he")

    def test_arabic(self):
        self.assertEqual(detect_language(ARABIC), "ar")

    def test_english(self):
        self.assertEqual(detect_language("what are your hours?"), "en")

    def test_one_latin_word_does_not_flip_a_hebrew_sentence(self):
        self.assertEqual(detect_language(HEBREW + " WhatsApp " + HEBREW), "he")

    def test_a_link_does_not_flip_a_hebrew_sentence_to_english(self):
        # Regression: a URL carries more Latin letters than a short Hebrew
        # sentence carries Hebrew ones, so counting them flipped the whole
        # message to "en" and prepare_outbound() returned it untouched - no
        # isolate, no RTL mark. "Text plus a link" is the single most common
        # real WhatsApp message shape.
        text = HEBREW + " https://example.com/prices " + HEBREW
        self.assertEqual(detect_language(text), "he")
        self.assertIn(LRI + "https://example.com/prices" + PDI, prepare_outbound(text))

    def test_an_email_or_phone_does_not_flip_detection_either(self):
        self.assertEqual(detect_language(HEBREW + " orders@example.com"), "he")
        self.assertEqual(detect_language(ARABIC + " +972-4-000-0000"), "ar")

    def test_no_script_at_all_falls_back_to_english(self):
        self.assertEqual(detect_language("2026"), "en")
        self.assertEqual(detect_language(""), "en")


class IsRtlTest(unittest.TestCase):
    def test_bare_subtags_and_full_locale_tags(self):
        for tag in ("he", "HE", "he-IL", "ar", "ar_EG", "fa-IR", "ur", "iw"):
            self.assertTrue(is_rtl(tag), tag)

    def test_ltr_and_empty_tags(self):
        for tag in ("en", "en-US", "ru", "", None):
            self.assertFalse(is_rtl(tag), tag)

    def test_dir_for_is_ready_for_an_html_attribute(self):
        self.assertEqual(dir_for("he-IL"), "rtl")
        self.assertEqual(dir_for("ar"), "rtl")
        self.assertEqual(dir_for("en"), "ltr")


class IsolateTest(unittest.TestCase):
    def test_phone_number_is_wrapped(self):
        out = prepare_outbound(HEBREW + " +972-4-000-0000", "he")
        self.assertIn(LRI + "+972-4-000-0000" + PDI, out)

    def test_url_is_wrapped(self):
        out = prepare_outbound(ARABIC + " https://example.com/prices", "ar")
        self.assertIn(LRI + "https://example.com/prices" + PDI, out)

    def test_bare_www_host_is_wrapped(self):
        out = isolate_ltr_runs(HEBREW + " www.example.com")
        self.assertIn(LRI + "www.example.com" + PDI, out)

    def test_email_address_is_wrapped(self):
        out = isolate_ltr_runs(ARABIC + " hello@example.com")
        self.assertIn(LRI + "hello@example.com" + PDI, out)

    def test_time_range_is_one_run_not_two(self):
        # The bug this guards: an RTL paragraph reorders "09:00-18:00" into
        # "18:00-09:00" and shows the closing time first.
        out = isolate_ltr_runs(HEBREW + " 09:00-18:00")
        self.assertIn(LRI + "09:00-18:00" + PDI, out)
        self.assertEqual(out.count(LRI), 1)

    def test_a_thousands_separator_does_not_split_the_number_run(self):
        # Regression: without the comma in the separator class this isolated as
        # "1," + LRI "250.00" PDI, putting the isolate boundary inside the
        # number - which reorders worse than leaving it alone.
        self.assertEqual(
            isolate_ltr_runs(HEBREW + " 1,250.00"),
            HEBREW + " " + LRI + "1,250.00" + PDI,
        )
        self.assertEqual(
            isolate_ltr_runs(HEBREW + " 1,250,000.50 " + HEBREW),
            HEBREW + " " + LRI + "1,250,000.50" + PDI + " " + HEBREW,
        )

    def test_running_twice_does_not_nest_isolates(self):
        once = prepare_outbound(HEBREW + " +972-4-000-0000", "he")
        self.assertEqual(prepare_outbound(once, "he"), once)

    def test_a_hand_wrapped_value_composes_with_prepare_outbound(self):
        # The reason this matters: a caller isolates a short id the pattern is
        # too strict to catch, then hands the whole sentence to
        # prepare_outbound. If it bailed out on seeing an isolate, everything
        # else in the sentence would silently go unprotected.
        text = f"{HEBREW} {isolate('A7')} {HEBREW} 09:00-18:00"
        out = prepare_outbound(text, "he")
        self.assertIn(LRI + "A7" + PDI, out, "the hand-wrapped id must survive")
        self.assertIn(LRI + "09:00-18:00" + PDI, out, "the range must still be isolated")
        self.assertEqual(out.count(LRI), 2)
        self.assertEqual(prepare_outbound(out, "he"), out, "and it is still idempotent")

    def test_a_hand_wrapped_value_is_never_wrapped_twice(self):
        out = prepare_outbound(HEBREW + " " + isolate("+972-4-000-0000"), "he")
        self.assertEqual(out.count(LRI), 1)
        self.assertIn(LRI + "+972-4-000-0000" + PDI, out)

    def test_an_unbalanced_isolate_is_left_alone(self):
        # Malformed input: an opening isolate with no closing one. Adding more
        # controls to it cannot help and makes the damage harder to see.
        broken = HEBREW + " " + LRI + "+972-4-000-0000"
        self.assertEqual(isolate_ltr_runs(broken), broken)

    def test_isolate_wraps_a_value_the_pattern_is_too_strict_to_catch(self):
        # "A7" is an order id, not a number run - the pattern needs 5+ chars.
        self.assertNotIn(LRI, isolate_ltr_runs(HEBREW + " A7"))
        self.assertEqual(isolate("A7"), LRI + "A7" + PDI)

    def test_isolate_accepts_a_number_and_never_double_wraps(self):
        self.assertEqual(isolate(42), LRI + "42" + PDI)
        self.assertEqual(isolate(isolate(42)), LRI + "42" + PDI)

    def test_format_time_range(self):
        self.assertEqual(format_time_range("09:00", "18:00"), LRI + "09:00-18:00" + PDI)
        self.assertEqual(
            format_time_range("09:00", "18:00", " - "), LRI + "09:00 - 18:00" + PDI
        )


class LineStartTest(unittest.TestCase):
    def test_line_starting_with_a_digit_gets_an_rtl_mark(self):
        self.assertTrue(prepare_outbound("2026 " + HEBREW, "he").startswith(RLM))

    def test_line_starting_with_a_latin_word_gets_an_rtl_mark(self):
        self.assertTrue(prepare_outbound("WhatsApp " + HEBREW, "he").startswith(RLM))

    def test_line_already_starting_rtl_is_left_alone(self):
        self.assertEqual(prepare_outbound(HEBREW, "he"), HEBREW)

    def test_every_line_is_handled_on_its_own(self):
        out = prepare_outbound(HEBREW + "\n2026 " + HEBREW + "\n\n" + ARABIC, "he")
        lines = out.split("\n")
        self.assertEqual(lines[0], HEBREW, "a strong-RTL line stays untouched")
        self.assertTrue(lines[1].startswith(RLM), "a digit-first line gets the mark")
        self.assertEqual(lines[2], "", "an empty line stays empty")
        self.assertEqual(lines[3], ARABIC, "an Arabic line stays untouched")

    def test_an_isolate_never_crosses_a_line_break(self):
        # A pair split over two lines would never balance, because the RTL mark
        # is applied line by line.
        out = prepare_outbound(HEBREW + " 09:00\n18:00 " + HEBREW, "he")
        for line in out.split("\n"):
            self.assertEqual(line.count(LRI), line.count(PDI), repr(line))

    def test_a_line_already_marked_is_not_marked_twice(self):
        once = prepare_outbound("2026 " + HEBREW, "he")
        self.assertEqual(force_rtl_paragraphs(once), once)


class PrepareOutboundTest(unittest.TestCase):
    def test_english_is_returned_untouched(self):
        text = "Call +972-4-000-0000 or visit https://example.com"
        self.assertEqual(prepare_outbound(text, "en"), text)

    def test_language_may_be_omitted_and_is_read_from_the_script(self):
        self.assertIn(LRI, prepare_outbound(HEBREW + " +972-4-000-0000"))
        self.assertEqual(
            prepare_outbound("Call +972-4-000-0000"), "Call +972-4-000-0000"
        )

    def test_empty_input_survives_every_entry_point(self):
        for func in (isolate_ltr_runs, force_rtl_paragraphs, strip_bidi):
            self.assertEqual(func(""), "")
            self.assertIsNone(func(None))
        self.assertEqual(prepare_outbound("", "he"), "")
        self.assertEqual(isolate(""), "")
        self.assertEqual(isolate(None), "")


class StripBidiTest(unittest.TestCase):
    def test_it_is_the_exact_inverse_of_prepare_outbound(self):
        original = HEBREW + " 09:00-18:00\n2026 " + HEBREW
        self.assertEqual(strip_bidi(prepare_outbound(original, "he")), original)

    def test_it_removes_legacy_embedding_marks_too(self):
        # RLE, PDF and LRM - the pre-isolate way of doing the same job, still
        # found in old translation files.
        legacy = "‫x‬‎y"
        self.assertEqual(strip_bidi(legacy), "xy")


class ParityWithJavaScriptTest(unittest.TestCase):
    """The npm package tervatrix-rtl-ui must produce byte-identical output.

    These expectations are maintained BY HAND against the JavaScript side, which
    is the limit of what this class can do: nothing here reads the other
    implementation, so it cannot notice the two drifting apart. On 2026-09-10 it
    was green while the packages disagreed on five inputs, because every case
    below is one they happen to agree on.

    ``test_parity.py`` is the half that closes that gap - it asserts against a
    fixture generated by running both implementations, which refuses to be
    written while they disagree. Keep both: this class documents the contract
    in readable form, that one enforces it.
    """

    CASES = (
        (HEBREW + " +972-4-000-0000", "he"),
        (ARABIC + " https://example.com/prices", "ar"),
        (HEBREW + " 09:00-18:00", "he"),
        ("2026 " + HEBREW, "he"),
        ("Call +972-4-000-0000 or visit https://example.com", "en"),
        # A thousands separator must not split the number run.
        (HEBREW + " 1,250.00", "he"),
    )

    EXPECTED = (
        HEBREW + " " + LRI + "+972-4-000-0000" + PDI,
        ARABIC + " " + LRI + "https://example.com/prices" + PDI,
        HEBREW + " " + LRI + "09:00-18:00" + PDI,
        RLM + "2026 " + HEBREW,
        "Call +972-4-000-0000 or visit https://example.com",
        HEBREW + " " + LRI + "1,250.00" + PDI,
    )

    # Language detection is part of the shared contract too: both sides must
    # agree on what an un-tagged string is written in.
    DETECT_CASES = (
        (HEBREW + " https://example.com/prices", "he"),
        (ARABIC + " https://shop.example.com/orders/12345", "ar"),
        (HEBREW + " WhatsApp " + HEBREW, "he"),
        ("what are your hours?", "en"),
        ("2026", "en"),
    )

    def test_detection_matches_javascript(self):
        for text, expected in self.DETECT_CASES:
            with self.subTest(text=repr(text)):
                self.assertEqual(detect_language(text), expected)

    def test_every_shared_case(self):
        for (text, lang), expected in zip(self.CASES, self.EXPECTED):
            with self.subTest(text=repr(text)):
                self.assertEqual(prepare_outbound(text, lang), expected)


if __name__ == "__main__":
    unittest.main()
