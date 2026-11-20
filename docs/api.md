# Avy resident API notes

Unofficial, reverse-engineered from the official app. Endpoints may change.

## Base URLs

- Production API: `https://api.avy.se/api`
- Payments: `https://payment.avy.se/api`

Authenticated requests use:

```
Authorization: Bearer <token>
```

## Authentication flow

The app supports BankID, email, SMS and magic-link login. BankID was the flow
used here and works entirely from a terminal:

| Step | Request | Result |
| --- | --- | --- |
| 1 | `POST /v1/auth/bankid/auth` with `{}` | `order_ref`, `auto_start_token`, `qr_start_token` |
| 2 | `GET /v1/auth/bankid/qr/{qr_start_token}` | `qr_code` (`bankid.…`) for the current second |
| 3 | user scans with BankID app and approves | — |
| 4 | `POST /v1/auth/bankid/collect` with `{"order_ref": …}` | `pending` / `complete` / `failed` |
| 5 | `POST /v1/auth/bankid/login` with `{"order_ref": …}` | `{"token": "…", "activated": true, "tenant_exists": true}` |

Notes:

- The QR is **animated** — the code changes every second. A static image is
  rejected by the BankID app.
- Field names are snake_case (`order_ref`), even though some validation errors
  print PascalCase (`OrderRef`).
- The JWT is long-lived (about 60 days in testing), but treat it as short-lived
  and re-login when calls return 401.
- Other login endpoints: `/v1/auth/email/auth` (`email`), `/v1/auth/email/login`
  (`email`, `code`), `/v1/auth/sms/auth` (`personal_number`, `phone_number`),
  `/v1/auth/magic-link/login` (`magic_link_token`). Availability depends on
  what the landlord enabled.

## Endpoint map

Selected paths recovered from the app binary:

```
/v1/auth/profile                 /v1/tenants                  /v1/lease-contract
/v1/invoice                      /v1/ledger/*                 /v1/message/*
/v1/notification/settings        /v1/booking                  /v1/config
/v1/features                     /v1/content/*                /v1/infocenter/*
/v2/contact-form*                /v2/booking*                 /v2/feature/config
```

Not all endpoints are enabled for every tenant — a disabled feature returns
`403 {"status":"feature not available"}`.

### Tenant resolution

`/v1/config?domain=<full My Pages hostname>` returns branding for landlords
that publish a browser portal (for example
`minasidor.bostadsbolaget.avy.se`). Some landlords have no public My Pages
hostname at all and use the app plus a tenant ID instead. Querying with a
wrong `subdomain` or `domain` returns
`{"status":"[GetByName] failed to fetch omni domain: record not found"}`.

## Case / fault reporting

Form types:

```
GET /v2/contact-form/type
GET /v2/contact-form/type/{form_type_id}?include_options=true
```

The `include_options=true` parameter is essential: without it, select fields
have no `options` array. Fields are identified by their `source`, not by UUID:

| source | meaning |
| --- | --- |
| `vitec_spati_system` | property / object |
| `vitec_space` | space (child of object) |
| `vitec_error_type` | fault type (child of space) |
| `vitec_description` | free-text description |
| `vitec_other` | master-key question (Ja/Nej) |
| `vitec_files` | attachments |

These names are landlord-specific. The app also contains `balder_*`,
`dynamics365_incident_*`, `fast2_*`, `fellowmind_*`, `lime_*`, `momentum_*`,
`pigello_*`, `tampuuri_*` and `unit4_*` variants. Never hardcode a field
source or UUID if the tool should work for multiple landlords — read the
schema with `?include_options=true` and follow `parent_field_uuid` links.

List and create:

```
GET  /v2/contact-form
POST /v2/contact-form
```

Create payload shape (validated against a real tenant):

```json
{
  "form_type_id": 24,
  "fields": {
    "<object field uuid>":      [{"value": "<option uuid>"}],
    "<space field uuid>":       [{"value": "<option uuid>"}],
    "<error field uuid>":       [{"value": "<option uuid>"}],
    "<description field uuid>": [{"value": "Kitchen tap is leaking"}],
    "<key field uuid>":         [{"value": "Nej"}]
  }
}
```

`fields` is a **map keyed by field UUID**, each value an array of objects with a
`value` key. For options with an empty `uuid` (such as Ja/Nej), send the label
text as the value.

The CLI discovers all UUIDs at runtime, so the same code works for other
landlords with different form configurations.
