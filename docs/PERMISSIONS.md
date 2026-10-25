# Permission Matrix

Source of truth for role-based authorization in Phase 1. The server-side
implementation is `src/musawiq/auth/permissions.py`; the dependency factory is
`src/musawiq/auth/service.py`.

## Roles

- `owner` — store owner.
- `manager` — delegated store operator.
- `analyst` — read-only analysis role.

## Matrix

| Action | Owner | Manager | Analyst |
|---|---|---|---|
| `read` | allow | allow | allow |
| `write` | allow | allow | deny |
| `publish_page` | allow | allow | deny |
| `submit_campaign` | allow | allow | deny |
| `approve_budget` | allow | allow | deny |
| `extend_test` | allow | allow | deny |
| `accept_recommendation` | allow | allow | deny |

## Decisions

- **Owner** has every action.
- **Manager** has every action. No action is withheld from Manager in the MVP
  matrix; Owner and Manager are equivalent for these seven actions. This is an
  explicit decision, not an oversight.
- **Analyst** has `read` only. Every other action is denied.

## Enforcement

- Authorization is checked server-side in the dependency factory
  `require(action)`; the role comes from the authenticated request context
  (`request.state.role`).
- A denied request returns HTTP 403 through the shared error envelope with a
  generic message. The response does not reveal whether the target resource
  exists.
- Every privileged action performed by a user must record the acting user in the
  audit trail (implemented by the audit service task).
