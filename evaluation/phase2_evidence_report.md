# Phase 2 — Evidence Extraction & Temporal Reconstruction Report
**Competition:** HackerRank Orchestrate (October 2026)  
**Challenge:** Ghost Data Still Exists  
**Execution Timestamp:** 2026-10-24T23:56:29.969602  
**Status:** COMPLETE & FULLY REPRODUCIBLE  

---

## 1. Executive Summary

Phase 2 constructed the unified multi-modal evidence intelligence layer, deterministic extractors for all heterogeneous evidence formats, and the temporal resource state machine bounded by each case's `audit_at`.

- **Total Evidence Files Manifested & Processed:** 94 / 94 (100.0%)
- **Total Evidence Observations Extracted:** 6,389
- **Evaluation Requests Audited:** 518
- **Sample Requests Audited:** 32
- **Evaluation Cases with Grounded Evidence:** 478 / 518
- **Total Unique Resources Evaluated at Audit Cutoff:** 965
- **Active Recreation Flows Detected (`REPORT_ACTIVE_DATA_FLOW`):** 65
- **Restore Risks Identified (`REPORT_RESTORE_RISK`):** 15
- **Conflicting Evidence Observations Resolved Deterministically:** 17
- **Stale / Post-Audit Evidence Items Dropped:** 37
- **Extraction Failures:** 0 (0.00%)

---

## 2. Modality-Specific Ingestion & Extraction Inventory

| Modality / Extension | Files Ingested | Parser / Method | Extracted Observations | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SQL / SQLite Snapshots (`.sql`)** | 24 | In-memory SQLite execution across 18 tables | 891 | 100% Extracted |
| **JSON Reports & Bundles (`.json`)** | 28 | Structured JSON deserializer & schema mapping | 888 | 100% Extracted |
| **Log Traces (`.log`)** | 26 | Key-value & JSON trace regex parser | 537 | 100% Extracted |
| **PDF Documents (`.pdf`)** | 4 | FlateDecode / ASCII85 stream decompressor | 9 | 100% Extracted |
| **Dashboard Screenshots (`.png`)** | 11 | Verified OCR console ground facts | 12 | 100% Extracted |
| **Text Handover Notes (`.txt`)** | 1 | Delimited shift handover parser | 41 | 100% Extracted |
| **Global System Activity Stream (`.csv`)** | 1 (4,011 rows) | Typed stream activity loader | 4,011 | 100% Extracted |

---

## 3. Extracted Observations Breakdown

### A. Observations by Target System
- **`account_service`**: 1,387 observations
- **`search_service`**: 1,378 observations
- **`analytics_platform`**: 805 observations
- **`security_service`**: 535 observations
- **`support_platform`**: 412 observations
- **`email_delivery_service`**: 368 observations
- **`integration_service`**: 325 observations
- **`cache_service`**: 284 observations
- **`archive_service`**: 196 observations
- **`object_store`**: 155 observations
- **`backup_service`**: 152 observations
- **`export_service`**: 117 observations
- **`account_replication_cluster`**: 55 observations
- **`backup_restore_service`**: 43 observations
- **`privacy_treatment_service`**: 42 observations
- **`support_storage_service`**: 39 observations
- **`identity_service`**: 29 observations
- **`downstream_delivery_service`**: 27 observations
- **`legal_service`**: 26 observations
- **`privacy_case_management`**: 10 observations
- **`marketing_platform`**: 2 observations
- **`account_failover_replica`**: 1 observations
- **`object_storage`**: 1 observations

### B. Observations by Data Category
- **`DELETE_RECORD`**: 890 observations
- **`USER_PROFILE`**: 810 observations
- **`UPDATE_RECORD`**: 672 observations
- **`SECURITY_AUDIT_LOG`**: 514 observations
- **`SYNC_RECORD`**: 447 observations
- **`INDEX_RECORD`**: 400 observations
- **`SEND_EMAIL`**: 368 observations
- **`SEARCH_INDEX_ENTRY`**: 310 observations
- **`REFRESH_CACHE`**: 284 observations
- **`ANALYTICS_PROFILE`**: 236 observations
- **`SUPPORT_MESSAGE`**: 209 observations
- **`RETAIN_RECORD`**: 206 observations
- **`ANONYMIZE_RECORD`**: 204 observations
- **`REDACT_RECORD`**: 173 observations
- **`CREATE_EXPORT`**: 155 observations
- **`CONNECTOR_SUBSCRIPTION`**: 138 observations
- **`CHECK_DATA_FLOW`**: 89 observations
- **`USER_EXPORT`**: 73 observations
- **`BACKUP_ARCHIVE`**: 63 observations
- **`DISABLE_DATA_FLOW`**: 36 observations
- **`BLOCK_RESTORE`**: 36 observations
- **`CHECK_RESTORE_ACCESS`**: 28 observations
- **`LINK_RESOURCE_IDENTITY`**: 12 observations
- **`SUPPORT_ATTACHMENT`**: 10 observations
- **`CLASSIFY_REQUEST`**: 10 observations
- **`DATA_FLOW`**: 7 observations
- **`LEGAL_HOLD_RECORD`**: 6 observations
- **`ACCOUNT_TOMBSTONE`**: 1 observations
- **`MARKETING_PROFILE`**: 1 observations
- **`RESTORE_BACKUP`**: 1 observations

### C. Observations by Proven State
- **`PRESENT`**: 4,407 observations
- **`UNKNOWN`**: 792 observations
- **`ABSENT`**: 504 observations
- **`ANONYMIZED`**: 285 observations
- **`ACTIVE`**: 132 observations
- **`REDACTED`**: 106 observations
- **`DISABLED`**: 85 observations
- **`BLOCKED`**: 78 observations

---

## 4. Temporal Reconstruction & Conflict Resolution Rules

1. **Temporal Cutoff Enforcement (`<= audit_at`):**
   - The state of each resource is established strictly by evidence captured or occurring at or before `audit_at`.
   - Any log entry, database snapshot, or activity event occurring after `audit_at` is strictly discarded from determining the case answer.

2. **Physical Snapshot vs. Activity Claim Hierarchy:**
   - Operational logs and workflow statuses claiming `SUCCESS` are treated as unverified assertions.
   - Physical database snapshots (SQL tables, replica dumps, JSON bundles, documents) take precedence over workflow claims.
   - If a deletion was logged at $T_1$, but a physical database replica or connector sync log at $T_2$ ($T_1 < T_2 \le \text{audit\_at}$) displays the record, the proven state is `PRESENT`.

3. **Recreation Risk & Flow Semantics:**
   - Connectors with `enabled=True` represent active data flows (`REPORT_ACTIVE_DATA_FLOW`, state `ACTIVE`).
   - Backup archives with `restore_allowed=True` represent restore risks (`REPORT_RESTORE_RISK`, state `ACTIVE`).
   - Compliant blocked backups (`restore_allowed=False`) evaluate to `BLOCKED`.

4. **Tombstone vs. Profile Separation:**
   - Account records where all direct identifiers (email, phone, name, hash) are stripped and only the internal `user_id` is preserved evaluate to `ACCOUNT_TOMBSTONE` with state `REDACTED`.
   - Analytics records unlinked from user identifiers evaluate to `ANALYTICS_PROFILE` with state `ANONYMIZED`.

---

## 5. Case Studies of Complex Reconstruction

### Case Study 1: `case_36` (aadebayo3975@fastmail.com)
- **Canonical User ID:** `user_34`
- **Audit Cutoff:** `2026-10-01T12:00:00+00:00`
- **Resources Evaluated:**
  - `account_service::account_5823 (ABSENT)`
  - `export_service::export_7689 (PRESENT)`
  - `search_service::search_5575 (PRESENT)`
  - `security_service::audit_record_2966 (PRESENT)`

### Case Study 2: `case_37` (abena.o189491@zoho.com)
- **Canonical User ID:** `user_35`
- **Audit Cutoff:** `2026-10-01T12:00:00+00:00`
- **Resources Evaluated:**
  - `account_service::account_5193 (ABSENT)`
  - `integration_service::data_flow_2528 (ACTIVE)`
  - `search_service::search_1934 (PRESENT)`
  - `security_service::audit_record_2019 (PRESENT)`

### Case Study 3: `case_38` (sipho.mokoena@gmail.com)
- **Canonical User ID:** `user_36`
- **Audit Cutoff:** `2026-10-01T12:00:00+00:00`
- **Resources Evaluated:**
  - `integration_service::data_flow_7495 (ACTIVE)`
  - `security_service::audit_record_633 (PRESENT)`
  - `account_service::account_2381 (ABSENT)`

### Case Study 4: `case_40` (choi.jihoon94@gmail.com)
- **Canonical User ID:** `user_38`
- **Audit Cutoff:** `2026-10-01T12:00:00+00:00`
- **Resources Evaluated:**
  - `search_service::search_3200 (PRESENT)`
  - `security_service::audit_record_8349 (PRESENT)`
  - `support_platform::support_4887 (PRESENT)`
  - `account_service::account_1810 (ABSENT)`

---

## 6. Adversarial Quality Gate Verification

- [x] Full adversarial test suite (`code/tests/test_evidence_temporal.py`) ran with 13/13 tests passing.
- [x] Full identity test suite (`code/tests/test_identity_engine.py`) ran with 11/11 tests passing (24/24 total tests).
- [x] Tested delete followed by recreation (recreation takes precedence).
- [x] Tested delete after `audit_at` (ignored; evaluated as `PRESENT` at cutoff).
- [x] Tested recreation after `audit_at` (ignored; evaluated as `ABSENT` at cutoff).
- [x] Tested active sync flows (`REPORT_ACTIVE_DATA_FLOW`) and restore risks (`REPORT_RESTORE_RISK`).
- [x] Tested contradictory workflow statuses (physical evidence overrides activity claims).
- [x] Tested unrelated user collisions (zero cross-user contamination).
- [x] Deterministic execution: no random seeds, no heuristic hallucination.

---

## 7. Next Steps (Phase 3 — Deletion Policy & Ordering Engine)

Proceed to Phase 3:
1. Implement `code/policy_engine.py` applying `deletion_rules.csv` (`rule_01` through `rule_15`) to proven resource snapshots.
2. Implement `code/remediation_planner.py` generating ordered remediation and verification steps.
3. Enforce strict step sequence: `FINDING` -> `REMEDIATION` -> `VERIFICATION`.
4. Enforce operation order:
   - Findings: `REPORT_REMAINING_RECORD` -> `REPORT_EXPOSED_PII` -> `REPORT_ACTIVE_DATA_FLOW` -> `REPORT_RESTORE_RISK`.
   - Remediation: `DISABLE_DATA_FLOW` -> `BLOCK_RESTORE` -> `DELETE_RECORD` -> `REDACT_RECORD` -> `ANONYMIZE_RECORD`.
   - Verification: `VERIFY_RECORD_ABSENT` -> `VERIFY_RECORD_PRESENT` -> `VERIFY_RECORD_REDACTED` -> `VERIFY_RECORD_ANONYMIZED` -> `VERIFY_DATA_FLOW_DISABLED` -> `VERIFY_RESTORE_BLOCKED`.
5. Enforce tie-breakers: `system_id` ascending, then `resource_id` ascending.
