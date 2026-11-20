#!/usr/bin/env python3
"""CLI for the Avy resident API.

Unofficial. Uses undocumented endpoints. Your BankID approval is still
required to obtain a token; this tool never bypasses BankID.

Configuration (environment variables):
  AVY_TOKEN_FILE   path to the JSON file written by avy-login.py
                   (default: ~/.avy/token.json, created with mode 0600)
  AVY_API_BASE     API base URL (default: https://api.avy.se/api)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("AVY_API_BASE", "https://api.avy.se/api")
TOKEN_FILE = Path(os.environ.get("AVY_TOKEN_FILE", "~/.avy/token.json")).expanduser()

# Form fields are discovered by their `source`, not by hardcoded UUIDs.
SOURCE_OBJECT = "vitec_spati_system"
SOURCE_SPACE = "vitec_space"
SOURCE_ERROR = "vitec_error_type"
SOURCE_DESCRIPTION = "vitec_description"
SOURCE_KEY = "vitec_other"


def get_token():
    try:
        return json.loads(TOKEN_FILE.read_text())["token"]
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit(
            f"No token found in {TOKEN_FILE}. Run avy-login.py first. ({exc})"
        )


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": "Bearer " + get_token(),
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def find_field(fields, source):
    for field in fields:
        if field.get("source") == source:
            return field
    raise SystemExit(f"Form has no field with source={source!r}")


def option_value(option):
    """The value accepted by the API for a select option."""
    return option.get("uuid") or option.get("option")


def resolve(field, requested=None, parent_value=None):
    options = field.get("options") or []
    if not options:
        raise SystemExit(f"No options returned for {field.get('label')!r}")
    if requested is None:
        if parent_value is None:
            return option_value(options[0])
        for option in options:
            if option.get("parent_option_uuid") == parent_value:
                return option_value(option)
        raise SystemExit(f"No option under parent {parent_value!r}")
    for option in options:
        if requested in (option.get("uuid"), option.get("external_id"), option.get("option")):
            return option_value(option)
    raise SystemExit(f"Unknown option {requested!r} for {field.get('label')!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profile", help="current tenant profile")
    sub.add_parser("tenants", help="tenancy / contract details")
    sub.add_parser("cases", help="list existing cases")
    sub.add_parser("case-types", help="list available case form types")
    sub.add_parser("invoices", help="list invoices")

    form = sub.add_parser("form", help="show a case form schema")
    form.add_argument("--type", type=int, help="form type id (default: first available)")
    form.add_argument("--options", action="store_true", help="include select options")

    raw = sub.add_parser("raw", help="call any API path")
    raw.add_argument("method")
    raw.add_argument("path")
    raw.add_argument("--body", help="JSON request body")

    create = sub.add_parser("case-create", help="report an issue")
    create.add_argument("description")
    create.add_argument("--type", type=int, help="form type id")
    create.add_argument("--object", help="property / object option")
    create.add_argument("--space", help="space option")
    create.add_argument("--error", dest="error_opt", help="error-type option")
    create.add_argument("--key", default="Nej", help="master key answer (Ja/Nej)")
    create.add_argument("--confirm", action="store_true", help="actually submit")

    args = parser.parse_args()

    if args.cmd == "profile":
        emit(call("GET", "/v1/auth/profile"))
    elif args.cmd == "tenants":
        emit(call("GET", "/v1/tenants"))
    elif args.cmd == "cases":
        emit(call("GET", "/v2/contact-form"))
    elif args.cmd == "case-types":
        emit(call("GET", "/v2/contact-form/type"))
    elif args.cmd == "invoices":
        emit(call("GET", "/v1/invoice"))
    elif args.cmd == "form":
        form_id = args.type or next(
            f["form_type_id"] for f in call("GET", "/v2/contact-form/type")
            if f.get("show_in_ui", True)
        )
        suffix = "?include_options=true" if args.options else ""
        emit(call("GET", f"/v2/contact-form/type/{form_id}{suffix}"))
    elif args.cmd == "raw":
        body = json.loads(args.body) if args.body else None
        emit(call(args.method.upper(), args.path, body))
    elif args.cmd == "case-create":
        form_id = args.type or next(
            f["form_type_id"] for f in call("GET", "/v2/contact-form/type")
            if f.get("show_in_ui", True)
        )
        schema = call("GET", f"/v2/contact-form/type/{form_id}?include_options=true")
        fields = schema["fields"]
        obj_field = find_field(fields, SOURCE_OBJECT)
        space_field = find_field(fields, SOURCE_SPACE)
        error_field = find_field(fields, SOURCE_ERROR)
        desc_field = find_field(fields, SOURCE_DESCRIPTION)
        key_field = find_field(fields, SOURCE_KEY)

        obj = resolve(obj_field, args.object)
        space = resolve(space_field, args.space, parent_value=obj)
        error = resolve(error_field, args.error_opt, parent_value=space)
        key = resolve(key_field, args.key)

        payload = {
            "form_type_id": form_id,
            "fields": {
                obj_field["uuid"]: [{"value": obj}],
                space_field["uuid"]: [{"value": space}],
                error_field["uuid"]: [{"value": error}],
                desc_field["uuid"]: [{"value": args.description}],
                key_field["uuid"]: [{"value": key}],
            },
        }
        if not args.confirm:
            print("DRY RUN - nothing submitted. Re-run with --confirm to create the case.\n")
            emit(payload)
            return
        emit(call("POST", "/v2/contact-form", payload))


if __name__ == "__main__":
    main()
