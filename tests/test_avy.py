import io
import json
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from avy import build_fields, main

# A different landlord / integration family (Lime) with the same shape as
# other integrations but no Vitec names or UUIDs.
LIME_SCHEMA = {
    "fields": [
        {"uuid": "lime-object-uuid", "source": "lime_object", "label": "Objekt",
         "type": "select", "required": True,
         "options": [{"uuid": "LIME-OBJ-1", "external_id": "obj-1",
                      "option": "Fastighet A"}]},
        {"uuid": "lime-room-uuid", "source": "lime_room", "label": "Utrymme",
         "type": "select", "required": True,
         "parent_field_uuid": "lime-object-uuid",
         "options": [{"uuid": "LIME-RUM-1", "external_id": "rum-1",
                      "option": "Kök", "parent_option_uuid": "LIME-OBJ-1"}]},
        {"uuid": "lime-type-uuid", "source": "lime_helpdesktype2", "label": "Typ",
         "type": "select", "required": True,
         "parent_field_uuid": "lime-room-uuid",
         "options": [{"uuid": "LIME-TYPE-1", "external_id": "typ-1",
                      "option": "Vattenläcka",
                      "parent_option_uuid": "LIME-RUM-1"}]},
        {"uuid": "lime-key-uuid", "source": "lime_key", "label": "Nyckel",
         "type": "select", "required": True,
         "options": [{"uuid": "", "option": "Ja"}, {"uuid": "", "option": "Nej"}]},
        {"uuid": "lime-desc-uuid", "source": "lime_description",
         "label": "Beskrivning", "type": "textarea", "required": True},
        {"uuid": "lime-files-uuid", "source": "lime_files", "type": "file",
         "required": False},
    ]
}

# A required child whose parent field is optional. The ancestor must still be
# resolved (and can be overridden) so the child has a parent option value.
OPTIONAL_ANCESTOR_SCHEMA = {
    "fields": [
        {"uuid": "opt-parent", "source": "demo_object", "label": "Objekt",
         "type": "select", "required": False,
         "options": [{"uuid": "OBJ-A", "option": "House A"},
                     {"uuid": "OBJ-B", "option": "House B"}]},
        {"uuid": "child-room", "source": "demo_room", "label": "Rum",
         "type": "select", "required": True,
         "parent_field_uuid": "opt-parent",
         "options": [{"uuid": "ROOM-A", "external_id": "room-a",
                      "option": "Kitchen", "parent_option_uuid": "OBJ-A"},
                     {"uuid": "ROOM-B", "external_id": "room-b",
                      "option": "Bath", "parent_option_uuid": "OBJ-B"}]},
    ]
}

def payload_from(output):
    """Return the JSON object printed after case-create's label summary."""
    match = re.search(r"^\{", output, re.MULTILINE)
    if not match:
        raise AssertionError(f"No payload in output: {output!r}")
    return json.loads(output[match.start():])


class BuildFieldsTests(unittest.TestCase):
    def test_override_must_name_a_known_field(self):
        with self.assertRaises(SystemExit):
            build_fields(LIME_SCHEMA, "text", overrides={"missing-field": "value"})

    def test_override_must_match_an_option(self):
        with self.assertRaises(SystemExit):
            build_fields(LIME_SCHEMA, "text",
                         overrides={"lime-room-uuid": "does-not-exist"})

    def test_resolves_optional_parent_and_filters_children(self):
        for overrides, expected in [
            ({}, {"opt-parent": "OBJ-A", "child-room": "ROOM-A"}),
            ({"opt-parent": "House B", "child-room": "room-b"},
             {"opt-parent": "OBJ-B", "child-room": "ROOM-B"}),
        ]:
            with self.subTest(overrides=overrides):
                self.assertEqual(build_fields(OPTIONAL_ANCESTOR_SCHEMA, "text", overrides=overrides),
                                 expected)

    def test_cycles_fail(self):
        schema = {"fields": [
            {"uuid": "a", "required": True, "parent_field_uuid": "b"},
            {"uuid": "b", "parent_field_uuid": "a"},
        ]}
        with self.assertRaisesRegex(SystemExit, "Circular"):
            build_fields(schema, "text")

    def test_explicit_positive_key_answer(self):
        fields = build_fields(LIME_SCHEMA, "text", key_answer="Ja")
        self.assertEqual(fields["lime-key-uuid"], "Ja")

    def test_invalid_key_answer_fails(self):
        with self.assertRaises(SystemExit):
            build_fields(LIME_SCHEMA, "text", key_answer="Kanske")

    def test_missing_negative_key_option_never_defaults_to_yes(self):
        schema = {"fields": [{"uuid": "key-question", "source": "other", "required": True,
                              "type": "select", "options": [{"option": "Ja"}]}]}
        with self.assertRaises(SystemExit):
            build_fields(schema, "text")

    def test_required_attachment_needs_an_explicit_value(self):
        schema = {"fields": [{"uuid": "attachment", "source": "lime_key_files",
                              "type": "file", "required": True}]}
        with self.assertRaisesRegex(SystemExit, "--set attachment="):
            build_fields(schema, "Sink is leaking")
        self.assertEqual(build_fields(schema, "text", overrides={"attachment": "file-id"}),
                         {"attachment": "file-id"})


class CliTests(unittest.TestCase):
    CASE_ARGS = ("case-create", "Sink is leaking", "--type", "7")

    def run_cli(self, argv, schema=LIME_SCHEMA, response=None):
        calls = []

        def fake_call(method, path, body=None, **kwargs):
            calls.append((method, path, body))
            if method == "GET" and path.startswith("/v2/contact-form/type/"):
                return schema
            return response if response is not None else {"ok": True}

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("avy.call", side_effect=fake_call), \
                mock.patch("sys.argv", ["avy.py", *argv]), \
                redirect_stdout(out), redirect_stderr(err):
            main()
        return out.getvalue(), err.getvalue(), calls

    def test_case_posts_only_after_confirmation(self):
        dry_out, err, calls = self.run_cli(self.CASE_ARGS)
        self.assertEqual(calls, [
            ("GET", "/v2/contact-form/type/7?include_options=true", None),
        ])
        self.assertIn("DRY RUN", dry_out + err)
        expected = payload_from(dry_out)
        self.assertEqual(expected, {
            "form_type_id": 7,
            "fields": {
                "lime-object-uuid": [{"value": "LIME-OBJ-1"}],
                "lime-room-uuid": [{"value": "LIME-RUM-1"}],
                "lime-type-uuid": [{"value": "LIME-TYPE-1"}],
                "lime-key-uuid": [{"value": "Nej"}],
                "lime-desc-uuid": [{"value": "Sink is leaking"}],
            },
        })

        out, _, calls = self.run_cli((*self.CASE_ARGS, "--confirm"),
                                     response={"id": 42})
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1], ("POST", "/v2/contact-form", expected))
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(out), {"id": 42})

    def test_case_set_canonicalizes_options_and_includes_optional(self):
        out, _, _ = self.run_cli((*self.CASE_ARGS,
                                  "--set", "lime-object-uuid=Fastighet A",
                                  "--set", "lime-room-uuid=rum-1",
                                  "--set", "lime-type-uuid=LIME-TYPE-1",
                                  "--set", "lime-files-uuid=attachment-1"))
        fields = payload_from(out)["fields"]
        self.assertEqual(fields["lime-object-uuid"], [{"value": "LIME-OBJ-1"}])
        self.assertEqual(fields["lime-room-uuid"], [{"value": "LIME-RUM-1"}])
        self.assertEqual(fields["lime-type-uuid"], [{"value": "LIME-TYPE-1"}])
        self.assertEqual(fields["lime-files-uuid"], [{"value": "attachment-1"}])

    def test_case_set_incompatible_option_fails(self):
        with self.assertRaises(SystemExit):
            self.run_cli((*self.CASE_ARGS,
                          "--set", "opt-parent=House B",
                          "--set", "child-room=Kitchen"),
                         schema=OPTIONAL_ANCESTOR_SCHEMA)

    def test_raw_write_is_dry_run_without_confirm(self):
        out, err, calls = self.run_cli(
            ("raw", "POST", "/v1/auth/example?private=fixture-query",
             "--body", '{"code": "fixture-code"}'))
        self.assertEqual(calls, [])
        self.assertIn("DRY RUN", out + err)
        self.assertNotIn("fixture-query", out + err)
        self.assertNotIn("fixture-code", out + err)

    def test_raw_write_with_confirm_posts(self):
        out, _, calls = self.run_cli(
            ("raw", "POST", "/v2/contact-form", "--body", '{"form_type_id": 7}',
             "--confirm"),
            response={"id": 42})
        self.assertEqual(calls, [
            ("POST", "/v2/contact-form", {"form_type_id": 7}),
        ])
        self.assertEqual(json.loads(out), {"id": 42})

    def test_raw_read_methods_need_no_confirm(self):
        for method in ("GET", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                out, _, calls = self.run_cli(
                    ("raw", method, "/v1/features"), response={"flags": []})
                self.assertEqual(calls, [(method, "/v1/features", None)])
                self.assertEqual(json.loads(out), {"flags": []})


if __name__ == "__main__":
    unittest.main()