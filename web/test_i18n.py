"""Tests for the bilingual UI string tables.

The copy deck exists twice: ``web/i18n_strings.py`` renders the first paint,
``static/js/i18n.js`` re-applies it at ``DOMContentLoaded`` — and again on every
EN⇄FA flip. Neither copy is generated from the other, so they drift, and a key
missing from *one* of them fails in a way Django will never tell you about:

  ``{{ i18n.key }}`` with no Python entry renders the node **blank** — silently,
      because Django template variable resolution fails soft.
  ``data-i18n="key"`` with no JS entry renders the node as **its own key name**:
      ``t()`` falls back to the key, and ``applyStatic()`` overwrites
      ``textContent`` unconditionally, so this happens on every single page load,
      not only when the reader switches language.

``docs/seo/SEO_AUDIT.md`` calls the JS copy "hand-maintained with no parity
test". This module is that test.

Split by *what could break* rather than by function:

``ServerRenderedTests``  keys the templates interpolate as ``{{ i18n.key }}``.
``ClientReappliedTests`` keys the templates hand to ``data-i18n`` and the
                         scripts hand to ``t()`` — both resolved by i18n.js.
``TableParityTests``     the two languages staying parallel, and the JS copy
                         staying a superset of the server copy.

Everything here scans the real files. Nothing is asserted from a hand-written
list of "important" keys: a list only catches the keys someone remembered to
add to it, and forgetting a key is precisely the failure being tested for.
"""

import os
import re

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

from web.i18n_strings import STRINGS

#: ``{{ i18n.key }}`` — resolved server-side.
RX_INTERPOLATE = re.compile(r"\{\{\s*i18n\.([a-zA-Z0-9_]+)")

#: ``data-i18n="key"`` — re-resolved client-side by ``applyStatic()``.
RX_DATA_I18N = re.compile(r'data-i18n="([a-zA-Z0-9_]+)"')

#: ``t("key")`` — a literal only. ``t("prefix_" + kind)`` is built at runtime
#: and cannot be checked statically; those prefixes are covered by the app's own
#: tests instead.
RX_T_LITERAL = re.compile(r'\bt\(\s*"([a-zA-Z0-9_]+)"\s*\)')


def _template_files():
    """Every template Django can actually render, app templates included."""
    dirs = [str(d) for d in settings.TEMPLATES[0]["DIRS"]]
    dirs += [os.path.join(app.path, "templates") for app in apps.get_app_configs()]
    for directory in dirs:
        for dirpath, _, filenames in os.walk(directory):
            if os.sep + "static" + os.sep in dirpath + os.sep:
                continue
            for name in filenames:
                if name.endswith(".html"):
                    yield os.path.join(dirpath, name)


def _referenced(pattern, roots, ext):
    """``{key: set(source files)}`` for every match of *pattern* under *roots*."""
    found = {}
    for path in roots:
        if not os.path.isfile(path) or not path.endswith(ext):
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for match in pattern.finditer(source):
            found.setdefault(match.group(1), set()).add(
                os.path.relpath(path, settings.BASE_DIR).replace(os.sep, "/")
            )
    return found


def _js_files():
    js_dir = os.path.join(settings.BASE_DIR, "static", "js")
    for name in sorted(os.listdir(js_dir)):
        if name.endswith(".js"):
            yield os.path.join(js_dir, name)


def _strip_js_comments(text):
    """Remove ``//`` and ``/* */`` comments, leaving string bodies intact.

    Needed because the literal is evaluated as Python, which has no line
    comments. A ``//`` inside a value (a URL, say) must not be mistaken for one,
    so the scan tracks string state exactly like the brace-matcher above.
    """
    out = []
    index = 0
    length = len(text)
    quote = None
    escaped = False
    while index < length:
        char = text[index]
        if quote:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "/" and text[index:index + 2] == "//":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and text[index:index + 2] == "/*":
            index += 2
            while index + 1 < length and text[index:index + 2] != "*/":
                index += 1
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _read_client_strings():
    """Parse the ``STRINGS`` literal out of ``static/js/i18n.js``.

    Brace-matched rather than regexed: the values contain punctuation that a
    naive pattern cannot be trusted to stop at, and a parse that silently
    returns ``{}`` would make every test below pass vacuously.
    """
    path = os.path.join(settings.BASE_DIR, "static", "js", "i18n.js")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    anchor = source.index("var STRINGS =")
    start = source.index("{", anchor)

    depth = 0
    end = None
    quote = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise AssertionError("could not brace-match STRINGS in static/js/i18n.js")

    # A JS object literal is a Python dict literal here — both tables are flat
    # maps of string to string — so the standard library is enough, once the
    # comments are gone.
    import ast

    literal = _strip_js_comments(source[start:end])
    # `key: "value"` -> `"key": "value"` so the literal parses as a dict.
    literal = re.sub(r"(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*):", r'\1"\2":', literal)
    try:
        strings = ast.literal_eval(literal)
    except (SyntaxError, ValueError) as exc:  # pragma: no cover - defensive
        raise AssertionError(f"could not parse STRINGS from i18n.js: {exc}") from exc
    if not isinstance(strings, dict) or set(strings) != {"en", "fa"}:
        raise AssertionError(f"i18n.js STRINGS must be exactly {{en, fa}}, got {set(strings)}")
    return strings


class _StringsTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `*_table`, not `client`/`server`: Django's TestCase already owns
        # ``self.client`` (the test client), and shadowing it fails confusingly.
        cls.server_table = STRINGS
        cls.client_table = _read_client_strings()
        cls.template_files = list(_template_files())
        cls.interpolated = _referenced(RX_INTERPOLATE, cls.template_files, ".html")
        cls.data_i18n = _referenced(RX_DATA_I18N, cls.template_files, ".html")
        cls.t_calls = _referenced(RX_T_LITERAL, list(_js_files()), ".js")

    def assertKeyExists(self, table, language, key, source):
        strings = table[language]
        self.assertIn(
            key,
            strings,
            f"{language}.{key} is missing (referenced by {sorted(source)[0]})",
        )
        self.assertTrue(
            strings[key].strip(),
            f"{language}.{key} is present but empty (referenced by {sorted(source)[0]})",
        )


class ServerRenderedTests(_StringsTestCase):
    """Keys interpolated as ``{{ i18n.key }}`` are resolved by the server."""

    def test_every_interpolated_key_exists_in_both_languages(self):
        for key, sources in sorted(self.interpolated.items()):
            for language in ("en", "fa"):
                with self.subTest(key=key, language=language):
                    self.assertKeyExists(self.server_table, language, key, sources)

    def test_interpolated_keys_are_also_known_client_side(self):
        # A key rendered server-side but absent from i18n.js survives the first
        # paint and is then erased by applyStatic() one tick later.
        for key, sources in sorted(self.interpolated.items()):
            for language in ("en", "fa"):
                with self.subTest(key=key, language=language):
                    self.assertKeyExists(self.client_table, language, key, sources)


class ClientReappliedTests(_StringsTestCase):
    """Keys the client re-resolves: ``data-i18n`` nodes and ``t()`` callers."""

    def test_every_data_i18n_key_exists_in_both_languages(self):
        for key, sources in sorted(self.data_i18n.items()):
            for language in ("en", "fa"):
                with self.subTest(key=key, language=language):
                    self.assertKeyExists(self.client_table, language, key, sources)

    def test_every_t_call_key_exists_in_both_languages(self):
        for key, sources in sorted(self.t_calls.items()):
            for language in ("en", "fa"):
                with self.subTest(key=key, language=language):
                    self.assertKeyExists(self.client_table, language, key, sources)

    def test_client_strings_reach_the_templates(self):
        # Keys that exist only on the client are fine, but a `t()` key nobody
        # renders and no template references is a string nobody can see —
        # usually a key renamed on one side only.
        referenced = set(self.data_i18n) | set(self.interpolated)
        orphan = set(self.client_table["en"]) - referenced - set(self.t_calls)
        # Player/studio chrome and progressive-enhancement strings are attached
        # by their own modules, so a handful of unreferenced keys is expected;
        # a large number means the two files have diverged.
        self.assertLess(
            len(orphan),
            60,
            f"{len(orphan)} client-only keys are referenced nowhere: {sorted(orphan)[:10]}",
        )


class TableParityTests(_StringsTestCase):
    """The two languages — and the two files — staying parallel."""

    def test_server_languages_carry_identical_keys(self):
        self.assertEqual(set(self.server_table["en"]), set(self.server_table["fa"]))

    def test_client_languages_carry_identical_keys(self):
        self.assertEqual(set(self.client_table["en"]), set(self.client_table["fa"]))

    def test_client_table_is_a_superset_of_the_server_table(self):
        # i18n.js re-applies every server-rendered string, so anything the
        # server can print must also exist client-side. The client may hold
        # extra keys (toasts, player labels) that only scripts ever ask for.
        for language in ("en", "fa"):
            with self.subTest(language=language):
                missing = set(self.server_table[language]) - set(self.client_table[language])
                self.assertFalse(
                    missing,
                    f"i18n.js is missing {language} keys the server renders: {sorted(missing)}",
                )

    def test_shared_keys_agree_on_english_where_both_sides_render_them(self):
        # A key rendered server-side *and* re-applied client-side must read the
        # same in English, or the copy silently changes when the page settles.
        # Keys used through only one path are allowed to differ (the server
        # short form of a validation message, say) and are not checked here.
        both = set(self.data_i18n) & set(self.interpolated)
        for key in sorted(both):
            with self.subTest(key=key):
                self.assertEqual(
                    self.server_table["en"].get(key),
                    self.client_table["en"].get(key),
                    f"{key} reads differently in the two tables",
                )

    def test_no_value_is_blank_in_either_table(self):
        for name, table in (("server", self.server_table), ("client", self.client_table)):
            for language, strings in table.items():
                for key, value in strings.items():
                    with self.subTest(table=name, language=language, key=key):
                        self.assertTrue(str(value).strip(), f"{name}.{language}.{key} is blank")

    def test_placeholders_are_balanced(self):
        for name, table in (("server", self.server_table), ("client", self.client_table)):
            for language, strings in table.items():
                for key, value in strings.items():
                    with self.subTest(table=name, language=language, key=key):
                        self.assertEqual(
                            str(value).count("{"),
                            str(value).count("}"),
                            f"{name}.{language}.{key} has an unbalanced placeholder",
                        )
