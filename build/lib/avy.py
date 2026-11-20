#!/usr/bin/env python3
"""CLI for the Avy resident API.

Unofficial. Uses undocumented endpoints. Your BankID approval is still
required to obtain a token; this tool never bypasses BankID.

Case forms are discovered dynamically from the live schema: field UUIDs,
option trees, parent dependencies and landlord-specific field sources are all
read at runtime, so this works across different Avy connected systems.

Configuration (environment variables):
  AVY_TOKEN_FILE   path to the JSON file written by avy-login.py
                   (default: ~/.avy/token.json, created with mode 0600)
  AVY_API_BASE     API base URL (default: https://api.avy.se/api)
"""
import argparse
import base64
import datetime
import json
import os
import re
import stat
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("AVY_API_BASE", "https://api.avy.se/api")
TOKEN_FILE = Path(os.environ.get("AVY_TOKEN_FILE", "~/.avy/token.json")).expanduser()
CAP_FILE = Path(os.environ.get("AVY_CAPABILITIES_FILE", "~/.avy/capabilities.json")).expanduser()

TEXT_TYPES = {"textarea", "text", "string", "number", "date", "email", "tel"}
KEY_HINTS = re.compile(r"(key|nyckel|access|other|tilltrade)", re.I)


def get_token():
    try:
        return json.loads(TOKEN_FILE.read_text())["token"]
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit(f"No token found in {TOKEN_FILE}. Run avy-login.py first. ({exc})")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + get_token(), "Accept": "application/json"}
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


def option_value(option):
    """Value accepted by the API for a select option."""
    return option.get("uuid") or option.get("option")


def resolve(field, requested=None, parent_value=None):
    """Resolve a user-supplied option by uuid, external id or label."""
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


def is_key_field(field):
    blob = " ".join(str(field.get(k, "")) for k in ("source", "label", "name")).lower()
    return bool(KEY_HINTS.search(blob))


def choose_value(field, chosen, description, key_answer):
    """Pick a value for one required field, honouring parent dependencies."""
    if not field.get("options"):
        return description
    parent = field.get("parent_field_uuid")
    options = field["options"]
    if parent and parent in chosen:
        compatible = [
            o for o in options
            if not o.get("parent_option_uuid") or o["parent_option_uuid"] == chosen[parent]
        ]
        if not compatible:
            raise SystemExit(
                f"No option for {field.get('label')!r} under selected parent {chosen[parent]!r}"
            )
        options = compatible
    if is_key_field(field):
        wanted = key_answer.strip().lower()
        for option in options:
            if option.get("option", "").strip().lower() == wanted:
                return option_value(option)
        for option in options:
            if option.get("option", "").strip().lower() in ("nej", "no", "false", "n"):
                return option_value(option)
    return option_value(options[0])


def build_fields(schema, description, key_answer="Nej", overrides=None):
    """Build the `fields` map for any landlord's case form."""
    overrides = overrides or {}
    required = [f for f in schema["fields"] if f.get("required")]
    chosen = {}
    pending = list(required)
    while pending:
        progress = False
        for field in list(pending):
            parent = field.get("parent_field_uuid")
            if parent and parent not in chosen and any(f["uuid"] == parent for f in pending):
                continue
            uuid = field["uuid"]
            if uuid in overrides:
                chosen[uuid] = overrides[uuid]
            elif field.get("type", "").lower() in TEXT_TYPES:
                chosen[uuid] = description
            else:
                chosen[uuid] = choose_value(field, chosen, description, key_answer)
            pending.remove(field)
            progress = True
        if not progress:
            raise SystemExit("Circular or unresolved parent fields in form schema")
    return chosen


def select_form_type(explicit=None):
    if explicit:
        return explicit
    types = call("GET", "/v2/contact-form/type")
    visible = [t for t in types if t.get("show_in_ui", True)]
    if not visible:
        raise SystemExit("No visible case form types for this tenancy")
    return visible[0]["form_type_id"]


def capabilities(refresh=False):
    """Show the locally cached capability map, or rebuild it from the API."""
    if refresh:
        data = {
            "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "token_expires_at": None,
        }
        token = get_token()
        try:
            segment = token.split(".")[1]
            segment += "=" * (-len(segment) % 4)
            exp = json.loads(base64.urlsafe_b64decode(segment)).get("exp")
            if exp:
                data["token_expires_at"] = datetime.datetime.fromtimestamp(
                    exp, datetime.timezone.utc).isoformat()
        except (IndexError, ValueError):
            pass
        try:
            data["flags"] = sorted(call("GET", "/v1/features").get("flags", []))
        except Exception as exc:
            data["flags_error"] = str(exc)
        try:
            data["form_types"] = [
                {"form_type_id": t.get("form_type_id"), "name": t.get("name")}
                for t in call("GET", "/v2/contact-form/type")
            ]
        except Exception as exc:
            data["form_types_error"] = str(exc)
        CAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        CAP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        CAP_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        print(f"Refreshed {CAP_FILE}")
    try:
        emit(json.loads(CAP_FILE.read_text()))
    except (OSError, ValueError):
        raise SystemExit(f"No capability map at {CAP_FILE}. Run avy-login.py or avy capabilities --refresh.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profile", help="current tenant profile")
    sub.add_parser("tenants", help="tenancy / contract details")
    sub.add_parser("cases", help="list existing cases")
    sub.add_parser("case-types", help="list available case form types")
    sub.add_parser("invoices", help="list invoices")
    caps = sub.add_parser("capabilities", help="show locally cached enabled features")
    caps.add_argument("--refresh", action="store_true", help="rebuild from the API")

    form = sub.add_parser("form", help="show a case form schema")
    form.add_argument("--type", type=int, help="form type id (default: first visible)")
    form.add_argument("--options", action="store_true", help="include select options")

    raw = sub.add_parser("raw", help="call any API path")
    raw.add_argument("method")
    raw.add_argument("path")
    raw.add_argument("--body", help="JSON request body")

    create = sub.add_parser("case-create", help="report an issue")
    create.add_argument("description")
    create.add_argument("--type", type=int, help="form type id")
    create.add_argument("--key", default="Nej", help="answer to key/access questions")
    create.add_argument("--set", action="append", default=[], metavar="UUID=VALUE",
                        help="override a field value (repeatable)")
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
    elif args.cmd == "capabilities":
        capabilities(refresh=args.refresh)
    elif args.cmd == "invoices":
        emit(call("GET", "/v1/invoice"))
    elif args.cmd == "form":
        suffix = "?include_options=true" if args.options else ""
        emit(call("GET", f"/v2/contact-form/type/{select_form_type(args.type)}{suffix}"))
    elif args.cmd == "raw":
        emit(call(args.method.upper(), args.path, json.loads(args.body) if args.body else None))
    elif args.cmd == "case-create":
        form_id = select_form_type(args.type)
        schema = call("GET", f"/v2/contact-form/type/{form_id}?include_options=true")
        overrides = {}
        for item in args.set:
            if "=" not in item:
                raise SystemExit(f"--set expects UUID=VALUE, got {item!r}")
            key, value = item.split("=", 1)
            overrides[key] = value
        fields = build_fields(schema, args.description, args.key, overrides)
        payload = {"form_type_id": form_id,
                   "fields": {uuid: [{"value": value}] for uuid, value in fields.items()}}
        if not args.confirm:
            print("DRY RUN - nothing submitted. Re-run with --confirm to create the case.\n")
            for field in schema["fields"]:
                if field["uuid"] in fields:
                    print(f"  {field.get('label') or field.get('source')}: {fields[field['uuid']]}")
            print()
            emit(payload)
            return
        emit(call("POST", "/v2/contact-form", payload))


if __name__ == "__main__":
    main()
