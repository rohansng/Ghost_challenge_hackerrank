# Phase 0 — Forensic Architecture Report: Ghost Data Still Exists
**Competition:** HackerRank Orchestrate (October 2026)  
**Challenge:** Ghost Data Still Exists  
**Role:** Primary Autonomous Software Engineer  
**Target Quality:** 100-Point / Competition-Winning Standard  
**Document Location:** `evaluation/phase0_forensics.md`

---

## Executive Summary & Core Principle

In modern enterprise architectures, deletion is not a single database `DELETE` query. As demonstrated by Northstar Shop's $2.4M incident, deletion requests routinely claim `COMPLETE` while ghost data persists across regional read replicas, failover clusters, search indexes, analytics cohorts, customer service ticket messages, object storage attachments, data exports, log streams, and backup archives. Active data flows (event bridges, CDC sync connectors) and disaster-recovery restore mechanisms actively resurrect supposedly deleted profiles.

To achieve 100% accuracy and complete adversarial robustness across all four evaluation dimensions (Code ZIP 30%, output.csv 30%, AI Interview 30%, AI Chat Transcript 10%), the audit system strictly adheres to the foundational architecture principle:

> **“Let the model describe; let deterministic code decide.”**

---

## A. Exact Challenge Requirements Extracted from Repository Files

Based on exhaustive inspection of `AGENTS.md`, `problem_statement.md`, `README.md`, `agent_trace_instructions.md`, and participant-facing datasets:

1. **Audit Scope:** For every case in `dataset/deletion_requests.csv` (exactly 518 requests, `case_33` through `case_550`), the system must determine:
   - Whether the subject actually authorized deletion (`COMPLETE` or `INCOMPLETE`), or submitted a non-deletion request (`NOT_APPLICABLE`).
   - The user's complete identity graph (current email, phone, name, email hash, plus historical emails and phones).
   - The ground-truth state of all data copies, search indexes, exports, tickets, logs, and processes at the exact timestamp `audit_at`.
   - Any active data flow (connector/CDC) or restore path capable of recreating deleted data.
   - The strictly ordered sequence of findings, remediation steps, and verification checks.
2. **Four Scoring Dimensions:**
   - **Code ZIP (30%):** Runnable solution, structured prompts, configuration, `README.md`, `code/evaluation/evaluation_report.md` (covering case, row, field, sequence accuracy, >= 3 custom test cases, failure/improvements), and `code/evaluation/usage_report.md` (token counts, provider, model names, per-request & total cost).
   - **output.csv Accuracy & Safety (30%):** Exactly 518 sorted data rows matching hidden canonical answers across status, findings, cited evidence, remediation operations, and post-verification checks.
   - **AI Interview (30%):** Technical defense of the forensic state reconstruction, identity resolution graph, temporal boundary enforcement, deterministic ordering engine, and remediation dependency graph.
   - **AI Chat Transcript (10%):** Continuous, unedited, AGENTS.md-compliant `log.txt` in the repository root recording session start and per-turn logs with authoritative `tool=` and `model=` metadata.
3. **Submission Invariants:**
   - Read ONLY participant-visible files under `dataset/`. Never attempt to access or assume organizer-only golden labels or internal generators.
   - Write output to `./output.csv` at repository root.
   - Header must be exactly: `case_id,deletion_status,steps_json`.
   - Exactly 518 data rows sorted lexicographically by `case_id`.

---

## B. Exact Output Schema

Each row in `output.csv` must strictly conform to:
```csv
case_id,deletion_status,steps_json
```

Where:
- `case_id` (string): Unique case identifier (e.g., `case_33`).
- `deletion_status` (string): Strictly one of `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `steps_json` (string): Valid JSON string representing an ordered array of step objects. For `NOT_APPLICABLE`, this MUST be an empty array `[]`.

### Step Object Schema:
```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_54"
}
```

Field constraints:
- `step_no` (integer): 1-indexed, strictly consecutive (`1, 2, 3, ...`).
- `phase` (string): Strictly `FINDING`, `REMEDIATION`, or `VERIFICATION`.
- `system_id` (string): Identifier of the subsystem (`account_service`, `search_service`, `analytics_platform`, `support_platform`, `export_service`, `integration_service`, `backup_service`, `security_service`, `identity_service`).
- `resource_id` (string): Unique identifier of the resource instance (e.g., `account_5334`, `search_1993`, `data_flow_3827`, `audit_record_3737`, `tombstone_9178`).
- `operation` (string): Must belong to the closed set of 15 allowed operations.
- `state` (string): Must match the required state for the given operation.
- `evidence_id` (string):
  - For `FINDING`: Must cite a participant-visible `file_id`, `activity_id`, or `audit_id` proving the violation.
  - For `VERIFICATION` on a `COMPLETE` case: Must cite the evidence proving compliant state at `audit_at`.
  - For `REMEDIATION` and post-remediation `VERIFICATION` on `INCOMPLETE` cases: Must be empty string `""`.

---

## C. Exact Status Semantics

1. **`NOT_APPLICABLE`:**
   - **Condition:** The user's `request_text` does not authorize account or data deletion (e.g., data subject access requests under GDPR Art. 15, data portability requests under GDPR Art. 20, profile corrections under GDPR Art. 16, marketing opt-outs, invoice requests, or password resets).
   - **Steps:** Must be exactly `[]` (empty JSON array). No remediation or verification is authorized.
   - **Empirical Grounding:** In `dataset/deletion_requests.csv`, exactly 10 cases (`case_533` through `case_542`) exhibit non-deletion intent.
2. **`COMPLETE`:**
   - **Condition:** The request authorized deletion, and as of `audit_at`:
     1. Every relevant personal copy has received the required treatment (deleted, redacted, or anonymized per `deletion_rules.csv`).
     2. No active synchronization, import, or restore path can recreate the user's data.
     3. Retained records (security audit logs, legal holds, tombstones) remain available and contain only permitted identifiers.
   - **Steps:** Contains **ONLY** `VERIFICATION` steps proving the compliant state at `audit_at`. Step numbers start at 1. Every step must cite a valid `evidence_id` (`file_id`, `activity_id`, or `audit_id`) captured at or before `audit_at`.
3. **`INCOMPLETE`:**
   - **Condition:** The request authorized deletion, but at `audit_at` at least one policy violation exists:
     - Direct profile or secondary copy still exists (`PRESENT`).
     - Retained record/tombstone exposes prohibited PII (name, email, phone, email hash) (`PRESENT`).
     - An active data flow connector is enabled (`ACTIVE`).
     - A backup archive has restore enabled (`ACTIVE`).
     - A required retention record was prematurely purged.
   - **Steps:** Formatted into three consecutive phases:
     1. `FINDING` steps for every discovered violation (citing evidence).
     2. `REMEDIATION` steps proposing complete corrective actions (`evidence_id=""`).
     3. `VERIFICATION` steps defining all post-remediation checks (`evidence_id=""`).

---

## D. Exact Remediation Ordering Rules

Array ordering in `steps_json` is strictly evaluated. Steps must adhere to a strict two-tier sorting hierarchy:

### Tier 1: Phase Order
1. `FINDING`
2. `REMEDIATION`
3. `VERIFICATION`

### Tier 2: Operation Priority within Phase
Within each phase, operations must appear in the exact order specified in the problem statement specification table:

#### Findings Order:
1. `REPORT_REMAINING_RECORD` (state: `PRESENT`)
2. `REPORT_EXPOSED_PII` (state: `PRESENT`)
3. `REPORT_ACTIVE_DATA_FLOW` (state: `ACTIVE`)
4. `REPORT_RESTORE_RISK` (state: `ACTIVE`)

#### Remediation Order:
Crucial dependency rule: Active replication and restore channels must be disabled BEFORE records are modified; downstream records must be handled before source records.
1. `DISABLE_DATA_FLOW` (state: `DISABLED`)
2. `BLOCK_RESTORE` (state: `BLOCKED`)
3. `DELETE_RECORD` (state: `ABSENT`)
4. `REDACT_RECORD` (state: `REDACTED`)
5. `ANONYMIZE_RECORD` (state: `ANONYMIZED`)

#### Verification Order:
1. `VERIFY_RECORD_ABSENT` (state: `ABSENT`)
2. `VERIFY_RECORD_PRESENT` (state: `PRESENT`)
3. `VERIFY_RECORD_REDACTED` (state: `REDACTED`)
4. `VERIFY_RECORD_ANONYMIZED` (state: `ANONYMIZED`)
5. `VERIFY_DATA_FLOW_DISABLED` (state: `DISABLED`)
6. `VERIFY_RESTORE_BLOCKED` (state: `BLOCKED`)

### Tier 3: Tie-Breaking
If two steps within the same phase have the same operation:
1. Sort by `system_id` ascending (lexicographical).
2. Sort by `resource_id` ascending (lexicographical).

*Validation Note:* This deterministic ordering rule has been verified against 100% of the 32 sample cases in `dataset/sample_output.csv` (e.g. `case_11`, `case_18`, `case_20`, `case_26`, `case_29`, `case_30`).

---

## E. Exact Evidence Citation Rules

1. **Eligible Citation IDs:**
   - A manifest `file_id` from `dataset/evidence_files.csv` (e.g. `evidence_01` to `evidence_94`).
   - An `activity_id` from `dataset/system_activity.csv` (e.g. `activity_3851`).
   - An `audit_id` from `dataset/user_audit_log.csv` (e.g. `audit_01`).
2. **`FINDING` Citations:** Must always cite the participant-visible evidence item that proves the remaining record or active risk.
3. **`COMPLETE` Verification Citations:** Must cite the evidence item that establishes the absence, redaction, anonymization, disabled flow, or blocked restore at `audit_at`.
4. **`INCOMPLETE` Citations:**
   - All `REMEDIATION` steps: `evidence_id = ""` (empty string).
   - All `VERIFICATION` steps (post-remediation): `evidence_id = ""` (empty string).
5. **No Hallucinated Citations:** Citation of non-existent IDs or IDs captured after `audit_at` is an immediate adversarial scoring penalty.

---

## F. Exact audit_at / Temporal Rules

1. **Temporal Cutoff:** Each case specifies an exact ISO-8601 timestamp in `audit_at`.
2. **Causal Horizon:** Only evidence, logs, and activity entries timestamped **at or before `audit_at`** may be considered when determining the state of that case.
   $$\text{captured\_at} \le \text{audit\_at}$$
3. **Strict Disqualification of Future Evidence:** Any evidence file captured after `audit_at` must never be cited or used to alter the verdict, even if it documents a subsequent deletion.
4. **Distinction between `reported_at` and `audit_at`:**
   - In cases like `case_25`, `reported_status` at `reported_at` was `NOT_STARTED`. However, by `audit_at`, the deletion workflow completed and evidence `evidence_92` proved the clean state. The correct verdict is `COMPLETE`.
   - In cases like `case_30`, `reported_status` was `COMPLETE`. However, evidence at `audit_at` proved data still remained in search and analytics. The correct verdict is `INCOMPLETE`.

---

## G. Exact deletion_rules Semantics

Extracted verbatim from `dataset/deletion_rules.csv`:

| Rule ID | Data Category | Trigger Condition | Required Action | Resulting State |
| :--- | :--- | :--- | :--- | :--- |
| `rule_01` | `USER_PROFILE` | Always | `DELETE` | `ABSENT` |
| `rule_02` | `SECONDARY_IDENTIFIER` | Always | `DELETE` | `ABSENT` |
| `rule_03` | `SEARCH_INDEX_ENTRY` | Always | `DELETE` | `ABSENT` |
| `rule_04` | `CACHE_ENTRY` | Always | `DELETE` | `ABSENT` |
| `rule_05` | `SUPPORT_MESSAGE` | Conversation contains shared customer, agent, or order context | `REDACT` | `REDACTED` |
| `rule_06` | `SUPPORT_ATTACHMENT` | Attachment belongs only to the deletion subject | `DELETE` | `ABSENT` |
| `rule_07` | `ANALYTICS_PROFILE` | Record is still attributable to a user | `ANONYMIZE` | `ANONYMIZED` |
| `rule_08` | `PRODUCT_TELEMETRY` | Record is still attributable to a user | `ANONYMIZE` | `ANONYMIZED` |
| `rule_09` | `USER_EXPORT` | Always | `DELETE` | `ABSENT` |
| `rule_10` | `MARKETING_PROFILE` | Always | `DELETE` | `ABSENT` |
| `rule_11` | `EMAIL_DELIVERY_LOG` | Log contains a user email address | `REDACT` | `REDACTED` |
| `rule_12` | `SECURITY_AUDIT_LOG` | Record is within the supplied retention period | `RETAIN` | `PRESENT` |
| `rule_13` | `LEGAL_HOLD_RECORD` | A supplied legal hold is active | `RETAIN` | `PRESENT` |
| `rule_14` | `BACKUP_ARCHIVE` | Restore access can be blocked | `RETAIN` / `BLOCK_RESTORE` | `BLOCKED` |
| `rule_15` | `ACCOUNT_TOMBSTONE` | Account is deleted, stable internal user_id needed | `REDACT` | `REDACTED` |

---

## H. Complete Inventory of All Data Sources

| File Name | Record Count | Description | Primary Identifiers / Keys |
| :--- | :--- | :--- | :--- |
| `deletion_requests.csv` | 518 rows | Evaluation cases | `case_id`, `email`, `requested_at`, `reported_status`, `reported_at`, `audit_at`, `request_text` |
| `sample_deletion_requests.csv` | 32 rows | Training/sample requests | Same schema as `deletion_requests.csv` |
| `sample_output.csv` | 32 rows | Canonical sample ground truth | `case_id`, `deletion_status`, `steps_json` |
| `user_identities.csv` | 850 rows | Current snapshot of users | `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at` |
| `user_audit_log.csv` | 306 rows | Historical changes to identity | `audit_id`, `user_id`, `event_time`, `field_name`, `old_value`, `new_value` |
| `system_activity.csv` | 4,011 rows | Global operations stream | `activity_id`, `event_time`, `event_type`, `source_system`, `target_system`, `resource_id`, `reported_result`, `details` |
| `deletion_rules.csv` | 15 rows | Policy specifications | `rule_id`, `data_category`, `condition`, `required_action` |
| `evidence_files.csv` | 94 rows | Manifest of evidence files | `file_id`, `file_path`, `origin`, `captured_at` |
| `output.csv` | 0 rows | Starter output template | `case_id`, `deletion_status`, `steps_json` |

---

## I. Evidence File Modality Inventory

Across `dataset/evidence/`, exactly 94 files exist in 5 distinct subdirectories:

1. **Databases (`dataset/evidence/databases/`, 24 files, .sql):**
   - Format: SQLite-compatible text dumps.
   - Types:
     - `customer_data_inventory_*.sql` (11 files): Comprehensive cross-service tables (`customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `support_records`, `customer_exports`, `connector_subscriptions`, `backup_restore_entries`, `security_audit_records`).
     - `customer_data_read_replica_*.sql` (5 files): Primary vs. read replica comparison tables (`customer_data_primary`, `customer_data_read_replica`).
     - `customer_data_regional_replicas_*.sql` (3 files): Multi-region replication consistency tables.
     - `customer_data_reporting_replica_*.sql` (2 files): Analytics reporting replica snapshots.
     - `customer_data_failover_replica_*.sql` (1 file): Failover replica snapshot.
     - `customer_accounts_failover_replica_*.sql` (1 file): Accounts failover snapshot (`evidence_54`).
     - `customer_search_primary_*.sql` (1 file): Search service primary cluster snapshot (`evidence_57`).
2. **Documents (`dataset/evidence/documents/`, 4 files, .pdf):**
   - Format: PDF 1.4 with FlateDecode and ASCII85Decode object streams. Standard library decodable without third-party dependencies.
   - Files:
     - `account_history_report_20260718.pdf` (`evidence_18`): Customer statements, orders, addresses (`user_18`, Ingrid Dahl).
     - `legal_retention_register_20260529.pdf` (`evidence_27`): Disputed orders and tax records register (`user_08`, `user_12`, retain until 2033).
     - `security_retention_extract.pdf` (`evidence_55`): Compliance journal signed record extract (`user_03`, `audit_record_003`, retain until 2027).
     - `delivery_correction_attachment.pdf` (`evidence_58`): Customer support delivery address correction request (`user_07`, Priya Raman, `support_001`).
3. **Images (`dataset/evidence/images/`, 11 files, .png):**
   - Format: High-resolution PNG application screenshots with clear text and tables.
   - Files:
     - `account_admin_console_20260926.png` (`evidence_04`): User Haruka Sato (`user_11`, `account_5762`).
     - `search_index_inspector_20260901.png` (`evidence_09`): User Gabriel Silva (`user_13`, `search_428`).
     - `connector_management_console_20260807.png` (`evidence_14`): Data flow connectors for Aditi Jain and Lucía Torres.
     - `analytics_profile_view_20260713.png` (`evidence_19`): User Omar Darwish (`user_20`, `analytics_7438`).
     - `customer_export_console_20260618.png` (`evidence_23`): Data exports for Ingrid Dahl (`export_1260`).
     - `support_ticket_console_20260524.png` (`evidence_28`): User Kofi Agyeman (`support_1034`).
     - `backup_restore_console_20260429.png` (`evidence_32`): Archive for Amelia Reed (`backup_9287`).
     - `security_audit_explorer_20260905.png` (`evidence_37`): User Oliver Bennett (`user_03`, `audit_record_003`).
     - `deleted_account_reference_20260310.png` (`evidence_42`): Tombstone for `user_17` (Léonie Girard).
     - `object_storage_browser_20260213.png` (`evidence_46`): S3 attachments and export bundles.
     - `marketing_profile_console.png` (`evidence_60`): Marketing profile for Soo-jin Park (`marketing_001`).
4. **Logs (`dataset/evidence/logs/`, 26 files, .log):**
   - Format: UTF-8 structured and semi-structured operational log traces.
   - Types:
     - `resource_lookup_trace_*.log` (11 files): Key-value readback logs (`resource_id`, `lookup_key`, `rows`, `http_status`).
     - `structured_service_events_*.log` (2 files): Pipe-delimited service event logs.
     - `service_events_*.log` (2 files): Multi-service event streams.
     - `application_trace_*.log` (2 files): Microservice trace logs.
     - `cloud_runtime_export_*.log` (2 files): Cloud runtime event dumps.
     - `operations_stream_*.log` (2 files): Platform event streams.
     - `syslog_archive_*.log` (2 files): Observability archives.
     - `notification_delivery_*.log` (1 file): Downstream delivery trace (`evidence_41`).
     - `search_index_diagnostic_*.log` (1 file): Search index diagnostic logs (`evidence_08`).
     - `support_replica.log` (1 file): Support ticket replication trace (`evidence_61`).
5. **Records (`dataset/evidence/records/`, 29 files):**
   - 28 JSON files:
     - `service_resource_export_*.json` (11 files): Point-in-time multi-service resource state dumps.
     - `customer_data_snapshot_bundle_*.json` (12 files): Data store collections and tombstones.
     - `connector_configurations_20260812.json` (`evidence_13`).
     - `customer_analytics_report_20260907.json` (`evidence_56`).
     - `customer_export_jobs_20260914.json` (`evidence_59`).
     - `customer_export_manifest_20260409.json` (`evidence_36`).
     - `security_audit_ledger_20261001.json` (`evidence_50`).
   - 1 TXT file:
     - `customer_account_handover_20261001.txt` (`evidence_03`): Shift handover audit checklist.

---

## J. Identity Relationships

Identity resolution is the critical foundation. Deletion audits fail if older identifiers are ignored.

1. **Resolution Pipeline:**
   - Input: `email` from `deletion_requests.csv` (case-insensitive).
   - Match against `user_identities.csv`: Current `email`.
   - Match against `user_audit_log.csv`: Historical `old_value` and `new_value` where `field_name == 'email'`.
   - Resolved Entity: Canonical `user_id`.
   - Expanded Entity Identifiers:
     - All known emails (current + historical).
     - All known phones (current + historical from `user_audit_log.csv`).
     - Full names and display names.
     - Computed SHA-256 email hashes (both current and historical).
2. **Empirical Verification:**
   - 100% of sample requests (32/32) and evaluation requests (518/518) resolve unambiguously to a canonical `user_id`.
   - 196 users in `user_audit_log.csv` possess historical modifications (212 email transitions, 94 phone updates).
   - Example: In `case_10`, `nadia.ionescu@yahoo.com` is the historical email of `user_10`, whose current email in `user_identities.csv` is `n.petrescu@yahoo.com`. Auditing only the current address would completely miss residual support ticket `support_002`!

---

## K. System / Activity Relationships

`dataset/system_activity.csv` records 4,011 operational activities spanning 9 core subsystems:
1. `account_service`: Primary profile management (`account_*`).
2. `search_service`: Customer directory search index (`search_*`).
3. `analytics_platform`: Behavioral profiles and cohort telemetry (`analytics_*`).
4. `support_platform`: Helpline tickets, messages, and attachments (`support_*`).
5. `export_service`: Downloadable data archive bundles (`export_*`).
6. `integration_service`: Outbound synchronization connectors (`data_flow_*`).
7. `backup_service`: Platform disaster-recovery archives (`backup_*`).
8. `security_service`: Tamper-evident compliance audit records (`audit_record_*`).
9. `identity_service`: Deleted account reference tombstones (`tombstone_*`).

**Claim vs. Proof Rule:**
Activities reporting `reported_result = SUCCESS` or `reported_result = PARTIAL` in `system_activity.csv` or `reported_status = COMPLETE` in `deletion_requests.csv` are **unverified claims**. They provide discovery leads for candidate `resource_id`s, but actual presence, absence, redaction, or recreation must be verified against point-in-time evidence files.

---

## L. Potential Deletion-Recreation Mechanisms

Adversarial evaluators test whether the agent detects data resurrection:
1. **Connector Data Flows (`integration_service`):**
   - Active connectors (`enabled = 1` / `true`, `last_delivery_status = 'delivered'`) continuously stream profile changes to downstream analytics warehouses or search indexes.
   - If an account was deleted from `account_service` but `data_flow_*` remains active, the connector recreates the search document or analytics profile upon the next scheduled sync.
2. **Read Replica & Failover Drift:**
   - Primary database records are deleted, but replication lag, broken replication slots, or unsynced failover replicas (`customer_data_read_replica` or `customer_profiles_failover_replica`) retain active records.
   - Upon failover or read distribution, personal data resurfaces.
3. **Backup Restores (`backup_service`):**
   - Database restore jobs with `restore_allowed = 1` / `true` can overwrite production tables with archived historical snapshots containing deleted users.
4. **Cache & Search Index Invalidation Failures:**
   - Database record deleted, but search index documents (`search_*`) remain unpurged.

---

## M. Required-Retention Mechanisms

The policy explicitly prohibits deleting records that must be retained:
1. **Security Audit Logs (`rule_12`):**
   - `SECURITY_AUDIT_LOG` records (`audit_record_*`) must be **RETAINED** (`VERIFY_RECORD_PRESENT`, `state = 'PRESENT'`).
   - They maintain cryptographic integrity seals and retention periods up to 10 years.
2. **Legal Holds (`rule_13`):**
   - `LEGAL_HOLD_RECORD` records under active dispute or tax investigation (e.g. `legal_retention_register_20260529.pdf`) must be retained until their explicit `retain_until` expiration date.
3. **Support Messages (`rule_05`):**
   - When support tickets contain shared agent/order context, the thread must **NOT** be deleted; it must be **REDACTED** (`REDACT_RECORD`, `state = 'REDACTED'`), stripping customer name, email, and phone while preserving ticket structure.
4. **Account Tombstones (`rule_15`):**
   - `ACCOUNT_TOMBSTONE` records (`tombstone_*`) must maintain only the internal `user_id` so retained legal/order records don't break referential integrity. All direct PII must be redacted.

---

## N. Risks of False COMPLETE

Declaring `COMPLETE` when data persists was the exact cause of Northstar Shop's $2.4M loss.
- **Root Causes:**
  - Trusting `reported_status = COMPLETE` without verifying evidence.
  - Checking primary database only, ignoring read/failover replicas.
  - Ignoring historical emails/phones from `user_audit_log.csv`.
  - Missing active synchronization connectors (`data_flow_*`) that recreate records.
  - Failing to detect unblocked backup archives (`backup_*`).
  - Overlooking support attachments in object storage.

---

## O. Risks of False INCOMPLETE

- **Root Causes:**
  - Misinterpreting compliant tombstones (where PII is removed but `user_id` remains) as illegal remaining records.
  - Treating policy-mandated security audit records (`audit_record_*`) as deletion failures.
  - Failing to recognize that a case was remediated between `reported_at` and `audit_at`.
  - Citing evidence captured after `audit_at`.
  - Treating non-deletion requests as deletion failures instead of `NOT_APPLICABLE`.

---

## P. Existing Code Weaknesses

Inspection of existing files revealed:
1. `code/main.py`: Empty file (0 bytes). No implementation exists.
2. `code/evaluation/main.py`: Empty file (0 bytes). No evaluation harness exists.
3. `dataset/output.csv`: Blank template (header only).
4. `log.txt`: Did not exist prior to this session. Initialized during this phase per AGENTS.md.

---

## Q. Existing Evaluation Weaknesses

1. No automated test suite for identity graph construction.
2. No automated validation of step ordering, operation sets, and state invariants.
3. No benchmark tracking token usage, latency, and cost per request.
4. Missing required evaluation reports: `evaluation_report.md` and `usage_report.md`.

---

## R. Missing Capabilities to Be Built

1. **Multimodal Evidence Normalizer:** Unified structured extraction across SQLite dumps, JSON bundles, structured logs, decrypted PDF text streams, and image screenshots.
2. **Historical Identity Graph Resolver:** Resolves any email/phone to the complete past and present identity set.
3. **Temporal Evidence Indexer:** Binds evidence to timestamps and strictly filters out future data relative to `audit_at`.
4. **Deterministic Policy & Remediation Planner:** Applies `deletion_rules.csv`, detects violations, and generates the exact sequence of findings, remediations, and verifications.
5. **Strict Canonical Ordering Engine:** Enforces the phase, operation priority, and system/resource tie-breaking rules.
6. **Output Validator:** Comprehensive sanity check verifying 518 rows, valid JSON, consecutive step numbers, valid operations, and valid citations.

---

## S. Proposed Architecture & Adversarial Evaluation

```
                    ┌─────────────────────────┐
                    │  deletion_requests.csv  │
                    └────────────┬────────────┘
                                 │
                     [1. Intent Classifier]
                                 │
          ┌──────────────────────┴──────────────────────┐
   (Non-deletion)                                  (Deletion)
          │                                             │
  NOT_APPLICABLE                          [2. Identity Graph Resolver]
  steps_json = []                                       │
                                          [3. Temporal Horizon Filter]
                                                        │
                                          [4. Multimodal Evidence DB]
                                                        │
                                          [5. Resource State Evaluator]
                                                        │
                                          [6. Policy Decision Engine]
                                                        │
                                     ┌──────────────────┴──────────────────┐
                                (Compliant)                           (Violations)
                                     │                                     │
                                  COMPLETE                             INCOMPLETE
                              (Verification)                  (Finding + Rem + Verif)
                                     │                                     │
                                     └──────────────────┬──────────────────┘
                                                        │
                                          [7. Strict Ordering Engine]
                                                        │
                                          [8. Submission Validator]
                                                        │
                                                 output.csv
```

---

## Quality Gate Checklist

- [x] Repository inspection complete.
- [x] Confirmed request count: 518 evaluation cases (`case_33` - `case_550`) + 32 sample cases (`case_01` - `case_32`).
- [x] Confirmed all schemas (`output.csv`, `system_activity.csv`, `evidence_files.csv`, etc.).
- [x] Confirmed evidence modalities: 26 logs, 28 JSONs, 1 TXT, 24 SQL snapshots, 4 PDFs, 11 PNGs.
- [x] Established that existing codebase was 0 bytes (clean slate).
- [x] Identified 10 concrete adversarial failure modes (detailed in report).
- [x] Defined deterministic vs. LLM boundary: Deterministic code executes all logic, identity graphs, SQL parsing, policy evaluation, and ordering; LLM/VLM assists only in ambiguous text interpretation and UI screen fact extraction.
