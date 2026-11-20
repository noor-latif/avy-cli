import unittest

from avy import option_value, resolve


FIELD = {
    "label": "Objekt",
    "options": [
        {"uuid": "OPT-A", "external_id": "a", "option": "Alpha"},
        {"uuid": "OPT-B", "external_id": "b", "option": "Beta",
         "parent_option_uuid": "OPT-A"},
    ],
}

KEY_FIELD = {
    "label": "Nyckel",
    "options": [
        {"uuid": "", "external_id": "", "option": "Ja"},
        {"uuid": "", "external_id": "", "option": "Nej"},
    ],
}


class OptionTests(unittest.TestCase):
    def test_option_value_prefers_uuid(self):
        self.assertEqual(option_value(FIELD["options"][0]), "OPT-A")

    def test_option_value_falls_back_to_label(self):
        self.assertEqual(option_value(KEY_FIELD["options"][1]), "Nej")

    def test_auto_first(self):
        self.assertEqual(resolve(FIELD), "OPT-A")

    def test_auto_with_parent(self):
        self.assertEqual(resolve(FIELD, parent_value="OPT-A"), "OPT-B")

    def test_explicit_by_label(self):
        self.assertEqual(resolve(FIELD, "Beta"), "OPT-B")

    def test_explicit_by_external_id(self):
        self.assertEqual(resolve(FIELD, "a"), "OPT-A")

    def test_explicit_key_label(self):
        self.assertEqual(resolve(KEY_FIELD, "Nej"), "Nej")

    def test_unknown_option_exits(self):
        with self.assertRaises(SystemExit):
            resolve(FIELD, "does-not-exist")


if __name__ == "__main__":
    unittest.main()
