# Phase 1 — Data Ingestion & Identity Graph Report
**Competition:** HackerRank Orchestrate (October 2026)  
**Challenge:** Ghost Data Still Exists  
**Execution Timestamp:** 2026-10-24T22:51:00.692507  
**Status:** COMPLETE & FULLY REPRODUCIBLE  

---

## 1. Executive Summary

Phase 1 established the deterministic data ingestion pipeline, explicit schemas, typed entity models, and the multi-hop temporal identity resolution graph.

Every case in `dataset/deletion_requests.csv` (518 requests) and `dataset/sample_deletion_requests.csv` (32 requests) was ingested, validated, and processed through the canonical `CaseContext` builder.

- **Total Evaluation Requests Processed:** 518
- **Total Sample Requests Processed:** 32
- **Unresolved Identities (Evaluation):** 0 (0.00%)
- **Unresolved Identities (Samples):** 0 (0.00%)
- **Ambiguous / Colliding Identities:** 0 (0.00%)
- **Non-Deletion Requests Identified (`NOT_APPLICABLE`):** 10 (10 cases: `case_533` - `case_542`)
- **Historical Email Matches (Evaluation):** 100
- **Current Email Matches (Evaluation):** 408
- **Parsing Errors / Malformed Rows:** 0 (0.00%)

---

## 2. Ingestion & Schema Diagnostics

| Dataset Source | Records Ingested | Schema Status | Duplicates / Anomalies Detected |
| :--- | :--- | :--- | :--- |
| `deletion_requests.csv` | 518 | Valid (7/7 columns) | 1 email repeated with distinct temporal timestamps (`case_33` & `case_52`) |
| `sample_deletion_requests.csv` | 32 | Valid (7/7 columns) | 0 duplicate case_ids |
| `user_identities.csv` | 850 | Valid (6/6 columns) | 0 duplicate user_ids, 0 email collisions |
| `user_audit_log.csv` | 306 | Valid (6/6 columns) | 196 distinct users with historical changes |
| `system_activity.csv` | 4,011 | Valid (8/8 columns) | Fully indexed across 9 systems |
| `deletion_rules.csv` | 15 | Valid (4/4 columns) | 15 closed policy rules |
| `evidence_files.csv` | 94 | Valid (4/4 columns) | 94 manifest files across 5 modalities |

---

## 3. Identity Resolution & Historical Reconstruction

The `IdentityEngine` builds an inverted index over both current snapshot records and chronologically ordered audit logs.

### A. Resolution Hierarchy
1. Exact direct match on canonical `user_id`.
2. Exact case-insensitive match on current primary `email`.
3. Historical match on historical `old_value` / `new_value` in `user_audit_log.csv`.
4. Phone and SHA-256 email hash corroboration.
5. Collision check: If any identifier is claimed by multiple distinct users, resolution halts and raises an explicit ambiguity flag rather than contaminating entity records.

### B. Difficult Case Studies

1. **Multi-Step Historical Email Transition (`user_10`, `case_10`):**
   - In `case_10`, the requested email is `nadia.ionescu@yahoo.com`.
   - In `user_identities.csv`, the user's current email is `n.petrescu@yahoo.com`.
   - `user_audit_log.csv` reveals a 2-hop transition:
     1. `2025-12-13T08:17:43Z`: `nadia.ionescu@yahoo.com` -> `nadia.petrescu@yahoo.com`
     2. `2026-04-12T14:38:26Z`: `nadia.petrescu@yahoo.com` -> `n.petrescu@yahoo.com`
   - *Result:* Resolves cleanly to `user_10` with historical provenance, enabling discovery of residual support ticket `support_002` created under the maiden address.

2. **The Repeated Subject with Different Temporal Cutoffs (`ingrid.dahl@outlook.com`):**
   - Appears in `case_52` (`requested_at`: 2026-06-16, `audit_at`: 2026-06-19).
   - Appears in `case_33` (`requested_at`: 2026-07-16, `audit_at`: 2026-07-19).
   - *Result:* The temporal identity engine evaluates each case strictly at its own `audit_at`, ensuring evidence from July (`account_history_report_20260718.pdf`) is excluded from the June audit.

3. **Non-Deletion Requests (`case_533` - `case_542`):**
   - The intent classifier scanned the multi-lingual request corpus and flagged exactly 10 requests that do not authorize deletion.
   - Example `case_535`: "I'd like to download my account information in a portable format. Please keep the account as it is." -> `PORTABILITY_REQUEST`.
   - Example `case_539`: "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it." -> `ACCESS_REQUEST`.
   - *Result:* Marked `is_deletion_authorized = False`, routed to `NOT_APPLICABLE` with `steps_json = []`.

---

## 4. Quality Gate Verification

- [x] Full unit test suite (`code/tests/test_identity_engine.py`) ran with 11/11 tests passing.
- [x] Zero unresolved identities across all 518 evaluation requests.
- [x] Zero unresolved identities across all 32 sample requests.
- [x] Collision prevention verified (no identity conflation).
- [x] Temporal identity reconstruction verified before and after `audit_at`.
- [x] Reproducibility: Deterministic code executes without random seeds or flaky heuristics.

---

## 5. Next Steps (Phase 2 — Multimodal Evidence Extraction & State Evaluation)

Proceed to Phase 2:
1. Ingest and parse SQLite dumps across primary, read replica, and failover topologies.
2. Ingest structured JSON bundles (`service_resource_export_*.json`, `customer_data_snapshot_bundle_*.json`).
3. Decode and extract text facts from all 4 PDFs and 11 UI screenshot consoles.
4. Construct the unified Resource State Model at `audit_at`.
