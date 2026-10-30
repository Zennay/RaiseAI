# Smart-home connector M1 — bounded light commands

Raise AI now has an **opt-in, server-side Home bridge adapter**, separate from
the existing zCloud and OpenRouter routes. This is a connector contract, **not**
an implementation of Google Home OAuth or a claim that a real Home device has
already been controlled.

## Safety boundary

- Default: `RAISE_HOME_EXECUTION_ENABLED` is not `1`, so no Home request is sent.
- The Watch still authenticates only to the Raise gateway. Its APK never
  contains Home credentials, Home device IDs or the Home bridge URL.
- The existing `smart_home` router must select
  `{route:"smart_home",target:"home.command",connector:"google_home"}`.
- Only one explicit command shape is allowed:
  `Zet de lampen in de woonkamer uit` (or `aan`); the same for
  `slaapkamer` and `keuken`. Each room must be separately mapped.
- No arbitrary prompts, JSON instructions, device IDs, URLs, shells, scripts,
  locks, thermostats or multi-device actions reach the bridge.
- The Home connector returns a disabled answer for unsupported commands.
  It **never** falls back to the AI model or the zCloud control route.
- The configured bridge must enforce its own provider/account authorization.
  Google Home account linking is not performed by Raise AI.

## VPS-only environment

Set these privately in the existing
`~/.config/raiseai/gateway.env` file **after** an authorized,
purpose-built Home bridge is installed and tested:

```dotenv
RAISE_HOME_EXECUTION_ENABLED=1
RAISE_HOME_BRIDGE_ORIGIN=https://your-authorized-home-bridge.example
RAISE_HOME_BRIDGE_TOKEN=REPLACE_WITH_PRIVATE_32_PLUS_CHARACTER_TOKEN
RAISE_HOME_DEVICES_JSON='{"woonkamer":"allowed-light-id"}'
```

The bridge origin must be a plain HTTPS origin (no path, userinfo, query or
fragment); only `http://127.0.0.1[:port]` is permitted for a local bridge.
A token must contain 32–256 non-whitespace characters. The allowlist permits
at most three room keys: `woonkamer`, `slaapkamer`, `keuken`. Each must map
to a distinct, bounded, server-configured device ID.

The gateway uses the fixed endpoint:

```http
POST /v1/light-actions
Authorization: Bearer <private-bridge-token>
Content-Type: application/json

{"device_id":"allowed-light-id","action":"turn_off"}
```

The bridge must return HTTP 200 or 202 with JSON:

```json
{"ok":true,"status":"accepted","device_id":"allowed-light-id","action":"turn_off"}
```

The bridge is never allowed to redirect this request. Raise AI enforces a
2.5-second deadline, a 4 KiB response budget, matching device/action fields
and exact `accepted` acknowledgement. `accepted` means only that the bridge
accepted the command — **not** that the physical light changed state.

On bridge authorization rejection, network failure, invalid response or
missing configuration, the Watch receives a short safe failure explanation,
without provider errors, credentials or an execution-success claim.

## Validation and release

- Gateway contract coverage: `gateway/test/home.test.mjs` in the existing
  `Raise gateway tests` workflow, including outer bearer authorization,
  bridge authorization, unsupported commands, routing isolation, malformed
  acknowledgement, oversized response, timeout and redirect refusal.
- The existing `quick_ai`, `deep_ai`, `current_info` and `zcloud_task`
  routes retain their current executor order and behavior.
- Source merge is **not** permission to enable Home control on production.
  Connecting a real Home bridge, binding Google Home credentials/device IDs
  and physically proving a harmless light action are separate release gates.
