# HackerRank Orchestrate (October 2026) — Ghost Data Still Exists

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Verification: Passed](https://img.shields.io/badge/Verification-100%25%20Passed-brightgreen.svg)]()
[![Deterministic: SHA--256](https://img.shields.io/badge/Deterministic-Bit--for--Bit-success.svg)]()
[![Challenge](https://img.shields.io/badge/HackerRank-Orchestrate-orange.svg)](https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)

> **Official Challenge URL:** [HackerRank Orchestrate October 2026: Ghost Data Still Exists](https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)  
> **Repository:** `https://github.com/rohansng/Ghost_challenge_hackerrank`

---

## 1. Executive Summary & Problem Context

In modern distributed commerce platforms, privacy deletion workflows frequently report **Complete** while personal data quietly persists in database replicas, access logs, support attachments, data warehouse exports, search indexes, analytics caches, cold storage archives, or system backups. Furthermore, active background synchronization pipelines, database failovers, and automated disaster-recovery restore processes can continuously recreate personal data that was previously erased from its primary source.

The **Ghost Data Still Exists** challenge requires constructing an autonomous deletion-audit agent. For every privacy request in `dataset/deletion_requests.csv` (518 evaluation cases), the agent must:

1. **Verify Authorization:** Determine whether the natural-language request actually authorizes deletion (as opposed to GDPR data access, rectification, export, or marketing opt-outs).
2. **Resolve Identity:** Reconstruct the subject's complete current and historical identity graph across historical name changes, email updates, and phone changes.
3. **Establish Temporal State:** Reconstruct the ground truth state of every copy of personal data strictly at the case's historical cutoff time (`audit_at`), ignoring subsequent modifications and rejecting unverified workflow claims.
4. **Detect Recreation Risks:** Analyze active data synchronization flows and backup restore paths to identify processes that could recreate deleted data.
5. **Apply Statutory Policy:** Enforce `deletion_rules.csv` across all identified resources, ensuring legal retention records are preserved while personal identifiers are redacted or anonymized, and account tombstones are properly stripped of direct identifiers.
6. **Plan Remediation & Verification:** For incomplete deletions, generate a safe, canonically ordered remediation plan (`FINDING` $\to$ `REMEDIATION` $\to$ `VERIFICATION`) and specify future verification checks. For complete deletions, return evidence-backed verification steps proving compliance.

---

## 2. End-to-End System Architecture

The engine is engineered with strict separation of concerns across 12 decoupled subsystems:

```mermaid
graph TD
    subgraph "1. Ingestion Tier"
        DR[deletion_requests.csv] --> L[DataLoader]
        UI[user_identities.csv] --> L
        UA[user_audit_log.csv] --> L
        SA[system_activity.csv] --> L
        DRU[deletion_rules.csv] --> L
        EV[evidence_files.csv] --> L
    end

    subgraph "2. Identity & Semantic Analysis"
        L --> IC[IntentClassifier: 6-Language Intent Engine]
        L --> IE[IdentityEngine: Multi-Hop Temporal Identity Graph]
    end

    subgraph "3. Multimodal Evidence Ingestion"
        L --> EN[EvidenceNormalizer]
        EN --> EX1[SqlExtractor: SQLite / Primary / Regional Replicas]
        EN --> EX2[JsonExtractor: Event payloads & system overrides]
        EN --> EX3[LogExtractor: Syslog RFC 5424 / Pipe / Bracketed Traces]
        EN --> EX4[TextExtractor: Support notes & [REDACTED] tokens]
        EN --> EX5[PdfExtractor: FlateDecode / Stream Decompression]
        EN --> EX6[ImageExtractor: Verified structural OCR facts]
    end

    subgraph "4. Deterministic Core & Decision Engine"
        IC & IE & EN --> TSM[TemporalStateMachine: Bounding t <= audit_at]
        TSM --> RA[RecreationAnalyzer: Directed DataFlowGraph & Cycle Detection]
        RA --> PE[PolicyEngine: deletion_rules.csv Predicate Evaluator]
        PE --> RP[RemediationPlanner: Canonical Phase & Operation Ordering]
        RP --> DE[DecisionEngine: 11-Point Proof Checklist & CaseProof]
    end

    subgraph "5. Validation & Serialization"
        DE --> OUT[output.csv: Exactly 518 Rows]
        OUT --> OV[OutputValidator: Strict Untrusted Schema & Proof Gate]
    end
```

---

## 3. Quickstart & CLI Execution

### 3.1 Prerequisites
- Python 3.10+ (Standard library only; zero external pip dependencies required).
- Tested across Linux, macOS, and Windows.

### 3.2 Running the Full Evaluation Pipeline
To execute the complete deletion audit across all 518 cases and write `output.csv`:

```bash
# Standard run (produces output.csv in root directory)
python code/main.py

# Full run with automatic strict output validation
python code/main.py --validate

# Verbose debug logging
python code/main.py -v

# Quiet mode (suppresses progress, emits errors only)
python code/main.py -q
```

### 3.3 Diagnostic Single-Case Audit
To inspect a specific case in detail, displaying the complete explainable 11-point proof checklist and steps:

```bash
python code/main.py --case-id case_33
```

Example diagnostic output:
```text
============================================================
CASE AUDIT DIAGNOSTIC: case_33 (ingrid.dahl@outlook.com)
============================================================
Requested At:    2026-07-16 08:00:00+00:00
Audit Cutoff:    2026-07-19 13:00:00+00:00
Reported Claim:  COMPLETE
Final Decision:  INCOMPLETE
Checklist Proof: {
  '1. Correct identity resolved': True,
  '2. Correct historical identifiers considered': True,
  '3. All relevant copies/resources identified': True,
  '4. Every applicable resource received required treatment': False,
  '5. Required retained records remain': True,
  '6. Retained records contain only permitted identifiers/data': True,
  '7. No relevant prohibited data remains': False,
  '8. No active sync/import/restore path can recreate prohibited data': True,
  '9. Required verification evidence exists': True,
  '10. Evidence is valid and within permitted temporal boundary': True,
  '11. No unresolved contradiction invalidates the proof': True
}
Decision Reasons: ['RESOURCE_NOT_TREATED', 'DATA_REMAINS']
Total Steps:     6
============================================================
```

### 3.4 Running the Test Suite
```bash
# Run all 102 unit, decision, planner, and adversarial regression tests
python -m unittest discover -s code/tests -p "test_*.py"

# Run adversarial validation suite directly
python code/run_phase7_audit.py

# Run AI architecture hardening audit
python code/run_phase8_audit.py
```

### 3.5 Validating `output.csv`
```bash
python code/output_validator.py output.csv dataset
```

---

## 4. Autonomous Agent Strategy & Pipeline Flow

The engine implements a rigorous 7-stage deterministic pipeline for each deletion request:

### Stage 1: Request Authorization Classification
The natural language in `request_text` is analyzed by [`IntentClassifier`](file:///d:/Hackerrank_hackathon/code/intent_classifier.py). The engine recognizes multilingual expressions across English, Spanish, French, German, Japanese, and Portuguese. Requests for account access, personal data export, rectification, or marketing communication opt-outs are immediately classified as `NOT_APPLICABLE` with `steps_json = []`.

### Stage 2: Multi-Hop Temporal Identity Resolution
Using [`IdentityEngine`](file:///d:/Hackerrank_hackathon/code/identity_engine.py), the request email is mapped to an internal `user_id`. The engine traverses `user_audit_log.csv` chronologically to reconstruct all historical emails, previous phone numbers, and pseudonymized hashes associated with the subject.

### Stage 3: Grounded Evidence Retrieval & Hash Indexing
[`EvidenceNormalizer`](file:///d:/Hackerrank_hackathon/code/evidence_normalizer.py) indexes observations across all 94 evidence files. To avoid missing secondary resource identifiers (e.g., account statements referenced only by account ID, or orders referenced by order ID), the engine executes a **2-pass transitive resource expansion**:
1. *Pass 1:* Matches direct subject identifiers (`user_id`, emails, phones, email hashes).
2. *Pass 2:* Discovers child resource IDs linked to the subject (e.g. `account_statement_1842`, `export_1260`) and pulls dependent evidence.

### Stage 4: Temporal Bounding & Replica Drift Analysis
The [`TemporalStateMachine`](file:///d:/Hackerrank_hackathon/code/temporal_state_machine.py) replays events in strict chronological order and cuts off evaluation at $t \le \text{audit\_at}$. Any evidence, workflow activity, or sync event timestamped strictly after `audit_at` is barred from altering the state. The machine reconciles replication drift across primary, regional, and reporting database replicas.

### Stage 5: Directed Recreation & Restore Analysis
The [`RecreationAnalyzer`](file:///d:/Hackerrank_hackathon/code/recreation_analyzer.py) constructs a directed `DataFlowGraph` from `system_activity.csv`. It identifies active recurring replication pipelines (e.g., `account_service` $\to$ `search_service`) and unblocked backup snapshots that pose a risk of repopulating erased personal records.

### Stage 6: Statutory Policy Evaluation
The [`PolicyEngine`](file:///d:/Hackerrank_hackathon/code/policy_engine.py) applies the rules in `deletion_rules.csv` to every reconstructed resource:
- **`DELETE`**: Entire resource must be eliminated (`ABSENT`).
- **`REDACT`**: Prohibited direct identifiers (name, email, phone) must be removed while preserving non-identifying data.
- **`ANONYMIZE`**: Subject identifiers must be irreversibly unlinked (`ANONYMIZED`).
- **`RETAIN`**: Statutory records (e.g., tax/transaction history) must be preserved (`PRESENT`) while redacting non-essential direct identifiers.
- **`ACCOUNT_TOMBSTONE`**: The stable internal `user_id` is preserved for referential integrity, but all direct PII (name, email, phone, email hash) must be excised.

### Stage 7: Canonical Remediation Planning & 11-Point Proof Verification
[`RemediationPlanner`](file:///d:/Hackerrank_hackathon/code/remediation_planner.py) and [`DecisionEngine`](file:///d:/Hackerrank_hackathon/code/decision_engine.py) evaluate the 11-point proof checklist. If any statutory condition fails, the case is declared `INCOMPLETE`, generating findings with evidence citations, safe remediation steps, and post-remediation verification checks. If all 11 conditions are met, the case is declared `COMPLETE` with evidence-backed verification steps proving the compliant state.

---

## 5. Deterministic Core vs. LLM/VLM Boundary (Zero-AI Invariant)

In compliance auditing, generative models present major risks: non-deterministic hallucinations, fabricated evidence IDs, and context truncation.

### The Zero-AI Boundary
Generative models are **strictly barred** from performing structured operations:
- **No LLM for CSV joins:** Lookups use $O(1)$ Python hash maps.
- **No LLM for timestamps:** Dates are parsed into timezone-aware UTC `datetime` objects and compared mathematically ($t \le \text{audit\_at}$).
- **No LLM for sorting:** Step ordering follows canonical integer phase ranks and alphabetical tie-breakers.
- **No LLM for compliance scoring:** Decisions are determined by the boolean 11-point proof checklist.
- **No LLM for evidence citations:** Cited IDs must match physical files or activity records.

### Candidate Observation Contract
When multimodal extraction models or OCR tools are used during forensic ingestion, their outputs are treated solely as untrusted `CandidateObservation` records:
```
LLM / Multimodal Parser
  │
  ▼
[CandidateObservation]
  │
  ▼
[ObservationValidator Gate] ──(Validates Schema, Manifest Grounding & Temporal Bounds)
  │
  ▼
[TemporalStateMachine]
  │
  ▼
[PolicyEngine]
  │
  ▼
[DecisionEngine] ──> Deterministic Compliance Verdict
```

---

## 6. Multimodal Evidence Handling

The platform dataset incorporates diverse evidence formats under `dataset/evidence/`:

| Modality | Extractor Module | Parsing Strategy & Forensic Invariant |
|:---|:---|:---|
| **SQL Snapshots** | [`SqlExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/sql_extractor.py) | Executes SQL scripts against in-memory SQLite instances; tracks schema alterations and detects replication drift across primary, regional, and reporting replicas. |
| **JSON / JSONL** | [`JsonExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/json_extractor.py) | Recursively searches structured JSON payloads for subject identifiers, field-level redactions, system overrides, and nested metadata. |
| **System Logs** | [`LogExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/log_extractor.py) | Parses RFC 5424 Syslog (`<15>1 ...`), pipe-delimited logs (`\| DEBUG \| service \| ...`), and bracketed headers (`[INFO] [service] [tr-...]`). Multi-line trace correlation tracks operations across services. |
| **Support Notes** | [`TextExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/text_extractor.py) | Scans plain text for direct identifiers, phone formats, and `[REDACTED]` markers. |
| **PDF Documents** | [`PdfExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/pdf_extractor.py) | Directly decompresses PDF content streams (`/FlateDecode` and `/ASCII85Decode`), extracting textual tokens, invoices, and customer receipts. |
| **Screenshots / Images** | [`ImageExtractor`](file:///d:/Hackerrank_hackathon/code/extractors/image_extractor.py) | Extracts tabular records, toggle configurations, and system IDs from administrative console captures. |

---

## 7. The 11-Point Statutory Proof Checklist

A case is declared `COMPLETE` if and only if **all 11 checklist conditions** evaluate to `True`:

```python
checklist = {
    "1. Correct identity resolved": c1,
    "2. Correct historical identifiers considered": c2,
    "3. All relevant copies/resources identified": c3,
    "4. Every applicable resource received required treatment": c4,
    "5. Required retained records remain": c5,
    "6. Retained records contain only permitted identifiers/data": c6,
    "7. No relevant prohibited data remains": c7,
    "8. No active sync/import/restore path can recreate prohibited data": c8,
    "9. Required verification evidence exists": c9,
    "10. Evidence is valid and within permitted temporal boundary": c10,
    "11. No unresolved contradiction invalidates the proof": c11,
}
```

If any condition evaluates to `False`, the case is classified as `INCOMPLETE`, and the specific root causes are mapped to `IncompleteReason` enum values (e.g., `RESOURCE_NOT_TREATED`, `ACTIVE_SYNC_FLOW`, `RESTORE_RISK`, `PROHIBITED_IDENTIFIER_REMAINS`).

---

## 8. Canonical Step Ordering & Validation Constraints

For compliance submissions, `output.csv` must follow strict formatting and ordering constraints:

### Phase Ordering
1. **`FINDING`** (Rank 1): Evidence-grounded reports of remaining records, exposed PII, active sync flows, or restore risks.
2. **`REMEDIATION`** (Rank 2): Proposed actions to disable data flows, block restores, delete records, or redact fields.
3. **`VERIFICATION`** (Rank 3): Checks verifying records are absent/redacted/anonymized or sync flows are disabled.

### Operation Priority Within Phases
- **Findings:** `REPORT_REMAINING_RECORD` (1) $\to$ `REPORT_EXPOSED_PII` (2) $\to$ `REPORT_ACTIVE_DATA_FLOW` (3) $\to$ `REPORT_RESTORE_RISK` (4).
- **Remediations:** `DISABLE_DATA_FLOW` (1) $\to$ `BLOCK_RESTORE` (2) $\to$ `DELETE_RECORD` (3) $\to$ `REDACT_RECORD` (4) $\to$ `ANONYMIZE_RECORD` (5).
- **Verifications:** `VERIFY_RECORD_ABSENT` (1) $\to$ `VERIFY_RECORD_PRESENT` (2) $\to$ `VERIFY_RECORD_REDACTED` (3) $\to$ `VERIFY_RECORD_ANONYMIZED` (4) $\to$ `VERIFY_DATA_FLOW_DISABLED` (5) $\to$ `VERIFY_RESTORE_BLOCKED` (6).

### Secondary Tie-Breaking & Step Numbering
When phase and operation ranks are identical, ordering breaks ties alphabetically by:
$$\text{system\_id} \to \text{resource\_id}$$
Steps are numbered consecutively starting from `1`. Proposed future remediation steps and post-remediation verification steps in `INCOMPLETE` cases use an empty string (`evidence_id=""`). Verification steps for `COMPLETE` cases cite participant-visible evidence.

---

## 9. Evaluation Metrics & Performance

The evaluation metrics from the final full-dataset run are detailed in [`evaluation/evaluation_report.md`](./evaluation/evaluation_report.md) and [`evaluation/usage_report.md`](./evaluation/usage_report.md):

| Metric | Measured Value | Standard / Target | Status |
|:---|:---:|:---:|:---:|
| **Total Evaluation Cases** | **518** | Exactly 518 | **PASSED** |
| **Output Schema Validation Errors** | **0** | 0 errors | **PASSED** |
| **Bit-for-Bit Determinism Across Runs** | **100.0%** | SHA-256 Identical | **PASSED** |
| **Unit & Adversarial Regression Tests** | **110 / 110** | 100% Passing | **PASSED** |
| **Execution Duration (518 Cases)** | **0.10 seconds** | < 120 seconds | **PASSED** |
| **Throughput** | **5,180 cases/sec** | Real-time audit | **PASSED** |
| **Runtime Model Calls** | **0** | Deterministic core | **PASSED** |
| **Runtime Token Cost** | **$0.00** | Budget compliant | **PASSED** |
| **Status Distribution** | `INCOMPLETE`: 349<br>`COMPLETE`: 159<br>`NOT_APPLICABLE`: 10 | Statistically sound | **PASSED** |

---

## 10. Packaging & Submission Instructions

### Packaging `code.zip`
To produce the clean submission ZIP conforming to AGENTS.md §6.9:

```bash
python package_submission.py
```

The packaging script verifies all competition constraints:
- Excludes `dataset/`
- Excludes virtual environments (`.venv`, `venv`, `node_modules`)
- Excludes bytecode caches (`__pycache__`, `*.pyc`)
- Excludes nested archives (`*.zip`, `*.tar`, `*.gz`)
- Bundles `README.md`, `AGENTS.md`, `problem_statement.md`, `evaluation/` reports, and all source code.

### Submission Artifacts Checklist
1. **`code.zip`**: Uploaded via the HackerRank platform UI.
2. **`output.csv`**: Exactly 518 data rows at the repository root.
3. **`chat_transcript`**: The root `log.txt` recording all development sessions and turns.
4. **AI Interview**: Ready to explain architecture, evidence handling, and decision proofs.

---

## 11. Known Limitations & Edge-Case Handling

1. **Unindexed Custom Binary Formats:** Evidence files must conform to supported modalities (PDF, image, text, log, JSON, SQL). Proprietary proprietary binary protocols require custom pre-processors.
2. **Ambiguous Historical Identity Chains:** If an audit log links two conflicting user IDs to the same email address without timestamps, the engine flags the conflict as an ambiguous identity exception and marks the case as `INCOMPLETE`.
3. **Replication Lag Approximations:** Replicas lacking explicit synchronization timestamps are evaluated against the most recent parent primary snapshot.

---

## 12. License & Integrity

This solution is authored specifically for the **HackerRank Orchestrate (October 2026)** competition.  
All participant-facing data in `dataset/` is strictly synthetic and fictional. No real personal data or secret credentials are used.
