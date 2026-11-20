# How this was discovered

No emulator, MITM proxy or jailbreak was needed. The whole API was recovered
from the app binary plus a few carefully-shaped requests.

## 1. Get the app bundle

The Play Store app is `com.avy_app` ("Avy – Resident app"). A bundle can be
fetched from an APK mirror or, preferably, from Google Play via a store client
such as Aurora Store. The bundle contains a base APK and config splits; the
Dart code lives in `lib/<abi>/libapp.so` inside the native split.

Check the signature with `apksigner verify --print-certs` or a tool like REA's
`inspect-apk-signature`. Google Play-signed apps show a Google signer;
third-party re-signs are a red flag.

## 2. Mine strings from the Dart snapshot

A Flutter AOT snapshot retains string literals:

```bash
unzip -p config.<abi>.apk lib/<abi>/libapp.so > libapp.so
strings -n 6 libapp.so > strings.txt
grep -Ei 'https?://|/v[0-9]/|authorization|x-api' strings.txt
```

This revealed the API base URLs, the full `/v1/` and `/v2/` route tables,
header names (`X-API-KEY`, `Authorization`), BankID model and field names, and
even internal Dart source paths such as `package:avy_flutter/...`.

## 3. Probe validation errors

Sending `{}` to an endpoint and reading the 400 response reveals required
field names. For example:

```
POST /v1/auth/bankid/collect  {}                     -> {"field":"OrderRef","error":"required"}
POST /v1/auth/bankid/collect  {"order_ref":"..."}    -> 200
POST /v2/contact-form         {}                     -> {"field":"FormTypeID","error":"required"}
POST /v2/contact-form         {"form_type_id":24,"fields":[]} -> Go type error revealing fields is a map
```

Go's JSON unmarshalling errors also disclosed the exact expected type:
`map[string][]contactv2.FilledOutField`.

## 4. Ask for options explicitly

`GET /v2/contact-form/type/24` returned fields without options. Adding
`?include_options=true` returned the dependent option tree with parent links.

## 5. Log in once

The BankID order endpoints work from plain HTTPS requests. The only step that
cannot be automated is the user's approval in the BankID app; the login helper
serves a live QR for that purpose. After approval, the returned bearer token
unlocks the rest of the API.

## Tools used

- `strings`, `unzip`, `curl` / Python `urllib`
- [REA](https://github.com/morluto/rea) (`inspect-apk-signature`,
  `identify-flutter-build`) and `jadx`
- `mitmproxy` was installed but ultimately unnecessary
- `qrcode` renders the live BankID QR as a local SVG without an imaging backend.

## Reproducing against another landlord

1. Obtain the app bundle and extract `libapp.so` for your device ABI.
2. Mine strings and confirm the API base URL (it may differ).
3. Log in and call `/v2/contact-form/type`.
4. Run `avy form --options` to inspect the schema before previewing a case.
