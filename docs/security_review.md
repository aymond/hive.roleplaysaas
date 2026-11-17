# Hivemind SaaS — Security Review

**Scope:** Backend (`backend/`), Frontend (`frontend/`), and Container/Deployment config (`Dockerfile`, `firebase.json`).  
**Target Environment:** Multi-tenant SFW SaaS on Google Cloud Platform (`europe-west4`).

---

## Summary of Findings

| Severity | Finding | Location | Status / Remediation |
| :--- | :--- | :--- | :--- |
| **CRITICAL** | Core CRUD & AI routes lack `get_current_user` & tenant isolation | [main.py](file:///Users/aymondelbridge/Projects/hivemind/backend/main.py) | Require `Depends(get_current_user)` on all user routes and migrate `StudioStorage` to tenant-scoped Firestore (`users/{uid}/...`). |
| **HIGH** | Wildcard CORS (`allow_origins=["*"]` + `allow_credentials=True`) | [main.py](file:///Users/aymondelbridge/Projects/hivemind/backend/main.py#L73-L77) | Restrict `allow_origins` to env-configured SaaS domains (`ALLOWED_ORIGINS`). |
| **HIGH** | Unauthenticated flat static media mount (`/media/generated`) | [main.py](file:///Users/aymondelbridge/Projects/hivemind/backend/main.py#L84-L87) | Serve generated PNGs & JSON metadata from a **private** GCS bucket (`public_access_prevention = "enforced"`) via short-lived Signed URLs. |
| **HIGH** | Client-supplied `customer_id` & `return_url` in Billing Portal | [billing.py](file:///Users/aymondelbridge/Projects/hivemind/backend/billing.py#L57-L65) | Resolve `stripe_customer_id` server-side from Firestore `users/{uid}` and validate `return_url` against `ALLOWED_ORIGINS`. |
| **MEDIUM** | `/api/system/config` exposes provider URLs & API keys; SSRF risk | [main.py](file:///Users/aymondelbridge/Projects/hivemind/backend/main.py), [models.py](file:///Users/aymondelbridge/Projects/hivemind/backend/models.py) | Gate `/api/system/config` with `Depends(require_admin)`, store API keys in GCP Secret Manager, and disallow user-supplied base URLs in SaaS mode. |
| **MEDIUM** | Local `backend/data/` could be copied into Docker image | [Dockerfile](file:///Users/aymondelbridge/Projects/hivemind/Dockerfile) | Added `.dockerignore` to exclude `backend/data/`, `.venv/`, `.git/`, and `.env`. |
| **MEDIUM** | `SAAS_AUTH_ENABLED` defaults to `"false"` | [auth.py](file:///Users/aymondelbridge/Projects/hivemind/backend/auth.py#L9) | Explicitly pinned to `"true"` in Cloud Run Terraform (`infra/main.tf`). |

---

## Verified Existing Controls
- **Pre-Flight SFW Moderation**: `enforce_moderation_or_422` ([moderation.py](file:///Users/aymondelbridge/Projects/hivemind/backend/moderation.py)) runs **before** LLM and image calls across chat, character cards, worlds/lore, and image synthesis.
- **Admin RBAC**: `/api/admin/moderation*` endpoints require `Depends(require_admin)` ([auth.py](file:///Users/aymondelbridge/Projects/hivemind/backend/auth.py#L69-L72)).
- **Webhook Integrity**: `/api/billing/webhook` ([billing.py](file:///Users/aymondelbridge/Projects/hivemind/backend/billing.py#L75-L93)) verifies `Stripe-Signature` via `stripe.Webhook.construct_event`.
- **Least-Privilege Cloud Run IAM**: Terraform (`infra/main.tf`) provisions a dedicated service account (`hivemind-api-sa`) with scoped Firestore, GCS bucket, Secret Manager, and Vertex AI roles—no `Owner`/`Editor` permissions.
