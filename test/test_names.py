import unittest

import pytest

from domain.names import is_command_name, parse_names, parse_swap, plain_text


class TestNames(unittest.TestCase):
    def test_parse_names(self):
        self.assertEqual(parse_names(" luca"), ["luca"])
        self.assertEqual(parse_names(" luca rossi"), ["luca rossi"])
        self.assertEqual(parse_names("a,b,c"), ["a", "b", "c"])
        self.assertEqual(parse_names("  a , b,, ,c ,"), ["a", "b", "c"])
        self.assertEqual(parse_names(""), [])
        self.assertEqual(parse_names("  "), [])
        self.assertEqual(parse_names(" , ,"), [])

    def test_is_command_name(self):
        self.assertTrue(is_command_name("/start"))
        self.assertFalse(is_command_name("luca"))
        self.assertFalse(is_command_name("lu/ca"))

    def test_parse_swap(self):
        self.assertEqual(parse_swap("scambia anna con bea"), ("anna", "bea"))
        self.assertEqual(parse_swap("scambia  anna  con  bea "), ("anna", "bea"))
        self.assertEqual(
            parse_swap("scambia luca rossi con bea"), ("luca rossi", "bea")
        )
        for text in [
            "scambia",
            "scambia anna",
            "scambia anna con",
            "scambia con anna",
            "scambia anna con bea con dino",
            "scambia anna conbea",
        ]:
            self.assertIsNone(parse_swap(text))


@pytest.mark.parametrize(
    "markdown, expected",
    [
        (None, None),
        ("", None),
        ("  \n ", None),
        ("None", None),
        (" None \n", None),
        ("**", None),
        ("plain  \n\n", "plain"),
        ("*bold* and _italic_ and `code`", "bold and italic and code"),
        ("see [the pitch](https://example.org/a_b) now", "see the pitch now"),
        ("[a](u) [b](v)", "a b"),
        ("two\nlines \n", "two\nlines"),
        ("Nonexistent", "Nonexistent"),
        (r"price \*5 and \_x\_ and \`k\` and \[a]", "price *5 and _x_ and `k` and [a]"),
        (r"\*not bold\*", "*not bold*"),
        ("campo_nord e campo_sud", "campo_nord e campo_sud"),
        ("a * b", "a * b"),
        ("a * b * c", "a * b * c"),
        ("5 * 3_", "5 * 3_"),
        ("*bold*", "bold"),
        ("_it_", "it"),
        ("_it_ campo_nord *b* a * b", "it campo_nord b a * b"),
        (r"*bold \* star* and _it_ [l_1](http://x/y_z)", "bold * star and it l_1"),
    ],
)
def test_plain_text(markdown, expected):
    assert plain_text(markdown) == expected
