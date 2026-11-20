#!/usr/bin/env python3
"""Unofficial Avy resident CLI. Login requires your own BankID approval."""
import argparse
import base64
import datetime
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("AVY_API_BASE", "https://api.avy.se/api").rstrip("/")
TOKEN_FILE = Path(os.environ.get("AVY_TOKEN_FILE", "~/.avy/token.json")).expanduser()
CAP_FILE = Path(os.environ.get("AVY_CAPABILITIES_FILE", "~/.avy/capabilities.json")).expanduser()

KEY_HINTS = re.compile(r"(key|nyckel|access|tilltr[aä]de|(?:\b|_)other\b)", re.I)
READ_COMMANDS = {
    "profile": ("/v1/auth/profile", "current tenant profile"),
    "tenants": ("/v1/tenants", "tenancy / contract details"),
    "cases": ("/v2/contact-form", "list existing cases"),
    "case-types": ("/v2/contact-form/type", "list available case form types"),
    "invoices": ("/v1/invoice", "list invoices"),
}


class ApiError(Exception):
    def __init__(self, message, body=None):
        super().__init__(message)
        self.body = body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_token():
    try:
        token = json.loads(TOKEN_FILE.read_text())["token"]
        if isinstance(token, str) and token.strip():
            return token
    except (OSError, KeyError, TypeError, ValueError):
        pass
    raise SystemExit(f"No usable token in {TOKEN_FILE}. Run avy-login first.")


def _response_body(response):
    raw = response.read().decode(errors="replace")
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def call(method, path, body=None, *, authenticated=True):
    if not path.startswith("/") or path.startswith("//"):
        raise SystemExit("API path must start with a single '/'")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer " + get_token()
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as resp:
            return _response_body(resp)
    except urllib.error.HTTPError as exc:
        with exc:
            raise ApiError(f"Avy returned HTTP {exc.code}", _response_body(exc)) from None
    except (OSError, ValueError):
        raise ApiError("Could not reach the Avy API") from None


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _field_value(field, parent, description, key_answer, requested):
    label = field.get("label") or field["uuid"]
    options = field.get("options") or []
    if not options:
        kind = (field.get("type") or "").lower()
        if kind == "select":
            raise SystemExit(f"No options returned for {label!r}")
        if requested is None and kind == "file":
            raise SystemExit(f"Set {label!r} explicitly with --set {field['uuid']}=VALUE")
        return description if requested is None else requested

    key_field = KEY_HINTS.search(" ".join(str(field.get(k, "")) for k in ("source", "label", "name")))
    answer = key_answer.strip().casefold()
    answers = {"nej", "no", "false", "n"} if answer == "nej" else {answer}
    for option in options:
        if option.get("parent_option_uuid") not in (None, "", parent):
            continue
        text = option.get("option") or ""
        value = option.get("uuid") or text
        if requested is not None:
            if not any(v not in (None, "") and str(v) == requested
                       for v in (option.get("uuid"), option.get("external_id"), text)):
                continue
        elif key_field and text.strip().casefold() not in answers:
            continue
        if value:
            return value
    raise SystemExit(f"No matching option for {label!r}")


def build_fields(schema, description, key_answer="Nej", overrides=None):
    """Select required and explicitly overridden fields after their parents."""
    fields = {f["uuid"]: f for f in schema["fields"]}
    overrides = overrides or {}
    chosen, visiting = {}, set()

    def choose(uuid):
        if uuid in chosen:
            return chosen[uuid]
        if uuid in visiting:
            raise SystemExit("Circular parent fields in form schema")
        if uuid not in fields:
            raise SystemExit(f"Unknown field UUID: {uuid}")
        field = fields[uuid]
        visiting.add(uuid)
        parent = field.get("parent_field_uuid")
        chosen[uuid] = _field_value(field, choose(parent) if parent else None,
                                    description, key_answer, overrides.get(uuid))
        visiting.remove(uuid)
        return chosen[uuid]

    for uuid, field in fields.items():
        if field.get("required") or uuid in overrides:
            choose(uuid)
    for uuid in overrides.keys() - fields.keys():
        raise SystemExit(f"Unknown field UUID: {uuid}")
    return chosen


def select_form_type(explicit=None):
    if explicit is not None:
        return explicit
    types = call("GET", "/v2/contact-form/type")
    visible = [t for t in types if t.get("show_in_ui", True)]
    if not visible:
        raise SystemExit("No visible case form types for this tenancy")
    return visible[0]["form_type_id"]


def write_private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    try:
        with temp:
            json.dump(data, temp, indent=2, ensure_ascii=False)
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def token_expiry(token):
    try:
        segment = token.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))["exp"]
        return datetime.datetime.fromtimestamp(exp, datetime.timezone.utc).isoformat()
    except (IndexError, KeyError, OSError, OverflowError, TypeError, ValueError):
        return None


def refresh_capabilities():
    data = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "token_expires_at": token_expiry(get_token()),
    }
    try:
        features = call("GET", "/v1/features")
        data["flags"] = sorted(features.get("flags", []))
        data["config_keys"] = sorted((features.get("config") or {}).keys())
    except (ApiError, AttributeError, TypeError) as exc:
        data["flags_error"] = str(exc) if isinstance(exc, ApiError) else "Unexpected features response"
    try:
        data["form_types"] = [
            {"form_type_id": t.get("form_type_id"), "name": t.get("name")}
            for t in call("GET", "/v2/contact-form/type")
        ]
    except (ApiError, AttributeError, TypeError) as exc:
        data["form_types_error"] = str(exc) if isinstance(exc, ApiError) else "Unexpected form types response"
    write_private_json(CAP_FILE, data)
    return data


def _cached_capabilities():
    try:
        return json.loads(CAP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(f"No capability map at {CAP_FILE}. Run avy capabilities --refresh.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, (_, help_text) in READ_COMMANDS.items():
        sub.add_parser(name, help=help_text)
    caps = sub.add_parser("capabilities", help="show locally cached enabled features")
    caps.add_argument("--refresh", action="store_true", help="rebuild from the API")

    form = sub.add_parser("form", help="show a case form schema")
    form.add_argument("--type", type=int, help="form type id (default: first visible)")
    form.add_argument("--options", action="store_true", help="include select options")

    raw = sub.add_parser("raw", help="call any API path")
    raw.add_argument("method")
    raw.add_argument("path")
    raw.add_argument("--body", help="JSON request body")
    raw.add_argument("--confirm", action="store_true", help="send a non-read request")

    create = sub.add_parser("case-create", help="report an issue")
    create.add_argument("description")
    create.add_argument("--type", type=int, help="form type id")
    create.add_argument("--key", default="Nej", help="answer to key/access questions")
    create.add_argument("--set", action="append", default=[], metavar="UUID=VALUE",
                        help="override a field value (repeatable)")
    create.add_argument("--confirm", action="store_true", help="actually submit")

    args = parser.parse_args()

    try:
        _run(args)
    except ApiError as exc:
        if exc.body is not None:
            emit(exc.body)
        raise SystemExit(str(exc)) from None
    except OSError as exc:
        raise SystemExit(str(exc)) from None


def _run(args):
    if args.cmd in READ_COMMANDS:
        emit(call("GET", READ_COMMANDS[args.cmd][0]))
    elif args.cmd == "capabilities":
        emit(refresh_capabilities() if args.refresh else _cached_capabilities())
    elif args.cmd == "form":
        suffix = "?include_options=true" if args.options else ""
        emit(call("GET", f"/v2/contact-form/type/{select_form_type(args.type)}{suffix}"))
    elif args.cmd == "raw":
        method = args.method.upper()
        try:
            body = json.loads(args.body) if args.body is not None else None
        except ValueError as exc:
            raise SystemExit(f"Invalid JSON for --body: {exc}") from None
        if method not in {"GET", "HEAD", "OPTIONS"} and not args.confirm:
            print("DRY RUN - nothing sent. Re-run with --confirm to send the request.", file=sys.stderr)
        else:
            emit(call(method, args.path, body))
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
