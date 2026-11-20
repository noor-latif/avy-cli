import unittest

from avy import build_fields, is_key_field, option_value, resolve


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
    "source": "vitec_other",
    "options": [
        {"uuid": "", "external_id": "", "option": "Ja"},
        {"uuid": "", "external_id": "", "option": "Nej"},
    ],
}

# A different landlord / integration family (Lime) with the same shape but
# completely different source names and UUIDs.
POSEIDON_SCHEMA = {
    "fields": [
        {"uuid": "lime-object-uuid", "source": "lime_object", "label": "Objekt",
         "type": "select", "required": True,
         "options": [{"uuid": "LIME-OBJ-1", "option": "Fastighet A"}]},
        {"uuid": "lime-room-uuid", "source": "lime_room", "label": "Utrymme",
         "type": "select", "required": True,
         "parent_field_uuid": "lime-object-uuid",
         "options": [{"uuid": "LIME-RUM-1", "option": "Kök",
                      "parent_option_uuid": "LIME-OBJ-1"}]},
        {"uuid": "lime-type-uuid", "source": "lime_helpdesktype2", "label": "Typ",
         "type": "select", "required": True,
         "parent_field_uuid": "lime-room-uuid",
         "options": [{"uuid": "LIME-TYPE-1", "option": "Vattenläcka",
                      "parent_option_uuid": "LIME-RUM-1"}]},
        {"uuid": "lime-key-uuid", "source": "lime_key", "label": "Nyckel",
         "type": "select", "required": True,
         "options": [{"uuid": "", "option": "Ja"}, {"uuid": "", "option": "Nej"}]},
        {"uuid": "lime-desc-uuid", "source": "lime_description", "label": "Beskrivning",
         "type": "textarea", "required": True},
        {"uuid": "lime-files-uuid", "source": "lime_files", "type": "file",
         "required": False},
    ]
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

    def test_key_field_detection(self):
        self.assertTrue(is_key_field(KEY_FIELD))


class GenericFormTests(unittest.TestCase):
    def test_build_fields_for_other_integration(self):
        fields = build_fields(POSEIDON_SCHEMA, "Sink is leaking")
        self.assertEqual(fields["lime-object-uuid"], "LIME-OBJ-1")
        self.assertEqual(fields["lime-room-uuid"], "LIME-RUM-1")
        self.assertEqual(fields["lime-type-uuid"], "LIME-TYPE-1")
        self.assertEqual(fields["lime-key-uuid"], "Nej")
        self.assertEqual(fields["lime-desc-uuid"], "Sink is leaking")
        self.assertNotIn("lime-files-uuid", fields)

    def test_overrides(self):
        fields = build_fields(POSEIDON_SCHEMA, "text",
                              overrides={"lime-room-uuid": "LIME-RUM-1"})
        self.assertEqual(fields["lime-room-uuid"], "LIME-RUM-1")

    def test_custom_key_answer(self):
        fields = build_fields(POSEIDON_SCHEMA, "text", key_answer="Ja")
        self.assertEqual(fields["lime-key-uuid"], "Ja")


if __name__ == "__main__":
    unittest.main()
