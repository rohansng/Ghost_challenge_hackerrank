"""
Log Evidence Extractor
Extracts structured observations from application, service, syslog, and lookup traces.
"""

import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from code.evidence_models import EvidenceObservation, ObservedState


def parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        clean = ts_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


class LogExtractor:
    def __init__(self, evidence_manifest: Dict[str, Dict[str, Any]]):
        self.manifest = evidence_manifest

    def extract_from_file(self, full_path: str, rel_path: str) -> List[EvidenceObservation]:
        observations = []
        meta = self.manifest.get(rel_path, {})
        file_id = meta.get("file_id", os.path.basename(full_path))
        manifest_captured_at = parse_iso(meta.get("captured_at"))

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return observations

        # Pass 1: Build trace_context to correlate across multi-line operations
        trace_context: Dict[str, Dict[str, Any]] = {}
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Check JSON line
            if "{" in line and "}" in line:
                j_start = line.find("{")
                j_end = line.rfind("}")
                if j_start != -1 and j_end != -1:
                    try:
                        j_payload = json.loads(line[j_start : j_end + 1])
                        tid = j_payload.get("trace_id") or j_payload.get("requestId")
                        if tid:
                            ctx = trace_context.setdefault(str(tid), {})
                            for k in ("email", "lookup_key", "customer_email", "subject_key", "match_key", "matched_value", "scan_key", "owner_key", "owner_email"):
                                v = j_payload.get(k)
                                if isinstance(v, str) and "@" in v:
                                    ctx["email"] = v.lower()
                            for k in ("user_id", "customer_reference", "subject_reference", "subject_ref", "correlation_key"):
                                v = j_payload.get(k)
                                if isinstance(v, str) and v.startswith("user_"):
                                    ctx["user_id"] = v
                            for k in ("correlation_key", "email_hash"):
                                v = j_payload.get(k)
                                if isinstance(v, str) and len(v) == 64:
                                    ctx["hash"] = v.lower()
                    except Exception:
                        pass

            trace_m = re.search(r'\b(?:trace_id|requestId)=(?:\"([^\"]*)\"|(\S+))', line)
            tid = None
            if trace_m:
                tid = trace_m.group(1) or trace_m.group(2)
            else:
                bracket_m = re.search(r'\[(tr-[^\]]+)\]', line)
                if bracket_m:
                    tid = bracket_m.group(1)
                else:
                    syslog_m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*<\d+>\d+\s+\S+\s+(\S+)\s+(tr-\S+)", line)
                    if syslog_m:
                        tid = syslog_m.group(3)
                    else:
                        pipe_m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*\|\s*\S+\s*\|\s*(\S+)\s*\|\s*(tr-\S+)", line)
                        if pipe_m:
                            tid = pipe_m.group(3)

            if tid:
                ctx = trace_context.setdefault(tid, {})
                clean_line = line.replace('\\"', '"')
                for k, v1, v2 in re.findall(r'(\b\w+)=(?:\"([^\"]*)\"|(\S+))', clean_line):
                    v = v1 if v1 else v2
                    if k in ("email", "lookup_key", "customer_email", "subject_key", "match_key", "matched_value", "subject_reference", "subject_ref", "scan_key", "owner_key", "owner_email") and "@" in v:
                        ctx["email"] = v.lower()
                    elif k in ("user_id", "customer_reference", "subject_reference", "subject_ref", "correlation_key") and v.startswith("user_"):
                        ctx["user_id"] = v
                    elif k in ("correlation_key", "email_hash") and len(v) == 64:
                        ctx["hash"] = v.lower()

        # Pass 2: Parse individual lines with inherited trace context
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            obs = self._parse_line(line, file_id, rel_path, manifest_captured_at, line_no, trace_context)
            if obs:
                observations.append(obs)

        return observations

    def _parse_line(
        self,
        line: str,
        file_id: str,
        rel_path: str,
        manifest_captured_at: Optional[datetime],
        line_no: int,
        trace_context: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[EvidenceObservation]:
        # Extract leading timestamp and optional bracketed / syslog / pipe metadata
        bracket_service = None
        bracket_tid = None
        bracket_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[([^\]]+)\]", line)
        if bracket_match:
            event_time = parse_iso(bracket_match.group(1))
            bracket_service = bracket_match.group(3)
            bracket_tid = bracket_match.group(4)
        else:
            syslog_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*<\d+>\d+\s+\S+\s+(\S+)\s+(tr-\S+)", line)
            if syslog_match:
                event_time = parse_iso(syslog_match.group(1))
                bracket_service = syslog_match.group(2)
                bracket_tid = syslog_match.group(3)
            else:
                pipe_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*\|\s*\S+\s*\|\s*(\S+)\s*\|\s*(tr-\S+)", line)
                if pipe_match:
                    event_time = parse_iso(pipe_match.group(1))
                    bracket_service = pipe_match.group(2)
                    bracket_tid = pipe_match.group(3)
                else:
                    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)", line)
                    event_time = parse_iso(ts_match.group(1)) if ts_match else manifest_captured_at

        obs_id = f"{file_id}_{line_no}"

        # 1. Check JSON lines (e.g. structured_service_events_*.log)
        if "{" in line and "}" in line:
            json_start = line.find("{")
            json_end = line.rfind("}")
            if json_start != -1 and json_end != -1:
                try:
                    payload = json.loads(line[json_start : json_end + 1])
                    return self._parse_json_log_payload(
                        payload, file_id, rel_path, event_time, manifest_captured_at, obs_id, line_no, trace_context
                    )
                except Exception:
                    pass

        # 2. Key-value pair extraction: key=val or key="val"
        clean_line = line.replace('\\"', '"')
        kv_pairs = {}
        for k, v1, v2 in re.findall(r'(\b\w+)=(?:"([^"]*)"|(\S+))', clean_line):
            kv_pairs[k] = v1 if v1 else v2

        # 3. Check for specific completed events
        resource_id = kv_pairs.get("resource_id")
        http_status = kv_pairs.get("http_status")
        result = kv_pairs.get("result")
        event = kv_pairs.get("event") or ""
        service = bracket_service or kv_pairs.get("service") or kv_pairs.get("system") or kv_pairs.get("function") or ""

        # Normalize service
        if "account" in service or "profile" in service:
            sys_id = "account_service"
            cat = "USER_PROFILE"
        elif "search" in service:
            sys_id = "search_service"
            cat = "SEARCH_INDEX_ENTRY"
        elif "support" in service:
            sys_id = "support_platform"
            cat = "SUPPORT_MESSAGE"
        elif "analytics" in service:
            sys_id = "analytics_platform"
            cat = "ANALYTICS_PROFILE"
        elif "connector" in service or "integration" in service:
            sys_id = "integration_service"
            cat = "CONNECTOR_SUBSCRIPTION"
        elif "backup" in service:
            sys_id = "backup_service"
            cat = "BACKUP_ARCHIVE"
        elif "security" in service or "audit" in service:
            sys_id = "security_service"
            cat = "SECURITY_AUDIT_LOG"
        elif "export" in service:
            sys_id = "export_service"
            cat = "USER_EXPORT"
        else:
            sys_id = service or "account_service"
            cat = "USER_PROFILE"

        # Check identifiers
        raw_ident = (
            kv_pairs.get("email")
            or kv_pairs.get("lookup_key")
            or kv_pairs.get("correlation_key")
            or kv_pairs.get("match_key")
            or kv_pairs.get("matched_value")
            or kv_pairs.get("subject_key")
            or kv_pairs.get("scan_key")
            or kv_pairs.get("owner_key")
            or kv_pairs.get("owner_email")
            or kv_pairs.get("subject_reference")
            or kv_pairs.get("subject_ref")
            or kv_pairs.get("customer_email")
        )
        email = None
        user_id = kv_pairs.get("customer_reference") or kv_pairs.get("subject_reference") or kv_pairs.get("subject_ref")
        hash_val = None

        if raw_ident:
            if "@" in raw_ident:
                email = raw_ident.lower()
            elif raw_ident.startswith("user_"):
                user_id = raw_ident
            elif len(raw_ident) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw_ident):
                hash_val = raw_ident.lower()

        # Inherit trace context if missing
        tid = bracket_tid or kv_pairs.get("trace_id") or kv_pairs.get("requestId")
        if tid and trace_context and tid in trace_context:
            t_ctx = trace_context[tid]
            if not email and "email" in t_ctx:
                email = t_ctx["email"]
            if not user_id and "user_id" in t_ctx:
                user_id = t_ctx["user_id"]
            if not hash_val and "hash" in t_ctx:
                hash_val = t_ctx["hash"]

        # Determine state
        state = ObservedState.UNKNOWN

        # HTTP status code checks (404 = ABSENT, 200 = PRESENT)
        if http_status:
            if http_status == "404":
                state = ObservedState.ABSENT
            elif http_status == "200":
                state = ObservedState.PRESENT

        # Result checks (hit, miss, FOUND, NOT_FOUND)
        elif result:
            res_upper = result.upper()
            if res_upper in ("NOT_FOUND", "MISS"):
                state = ObservedState.ABSENT
            elif res_upper in ("FOUND", "HIT"):
                state = ObservedState.PRESENT

        # Detector / PII scan checks
        elif kv_pairs.get("detector") == "direct_identifier" or kv_pairs.get("direct_identifiers") == "1" or "pii_scan" in event or "identity_scan" in event:
            state = ObservedState.PRESENT

        # Redacted message check
        elif kv_pairs.get("message_text") == "[REDACTED]":
            state = ObservedState.REDACTED

        # Security audit log integrity check
        elif sys_id == "security_service" and (kv_pairs.get("integrity_check") == "passed" or kv_pairs.get("rows") == "1"):
            state = ObservedState.PRESENT

        # Export availability check
        elif "available" in kv_pairs:
            is_avail = kv_pairs["available"].lower() == "true"
            state = ObservedState.PRESENT if is_avail else ObservedState.ABSENT

        # Rows check (rows=0 -> ABSENT, rows=1 -> PRESENT)
        elif "rows" in kv_pairs:
            rows_val = kv_pairs["rows"]
            if rows_val == "0":
                state = ObservedState.ABSENT
            elif rows_val == "1":
                state = ObservedState.PRESENT

        # Connector enabled check
        elif "enabled" in kv_pairs:
            is_enabled = kv_pairs["enabled"].lower() == "true"
            state = ObservedState.ACTIVE if is_enabled else ObservedState.DISABLED

        # Backup restore_allowed or deletion_block check
        elif "restore_allowed" in kv_pairs:
            is_allowed = kv_pairs["restore_allowed"].lower() == "true"
            state = ObservedState.ACTIVE if is_allowed else ObservedState.BLOCKED
        elif "deletion_block" in kv_pairs:
            is_blocked = kv_pairs["deletion_block"].lower() == "true"
            state = ObservedState.BLOCKED if is_blocked else ObservedState.ACTIVE

        # Support marker check
        elif "marker_found" in kv_pairs:
            marker = kv_pairs["marker_found"].lower() == "true"
            state = ObservedState.ABSENT if marker else ObservedState.PRESENT

        supp_idents = []
        if hash_val:
            supp_idents.append(hash_val)

        if resource_id and state != ObservedState.UNKNOWN:
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"line:{line_no}",
                extraction_method="log_kv_parser",
                captured_at=manifest_captured_at,
                event_time=event_time,
                system_id=sys_id,
                resource_id=resource_id,
                resource_type=cat,
                data_category=cat,
                observed_state=state,
                user_id=user_id,
                matched_identifier=email or hash_val or user_id,
                supporting_identifiers=supp_idents,
                raw_payload=kv_pairs,
                semantic_interpretation=f"Log event {event}: {resource_id} -> {state.value}",
            )

        return None

    def _parse_json_log_payload(
        self,
        payload: Dict[str, Any],
        file_id: str,
        rel_path: str,
        event_time: Optional[datetime],
        manifest_captured_at: Optional[datetime],
        obs_id: str,
        line_no: int,
        trace_context: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[EvidenceObservation]:
        res_id = payload.get("resource_id")
        svc = payload.get("service") or payload.get("logger") or ""
        raw_ident = (
            payload.get("match_key")
            or payload.get("lookup_key")
            or payload.get("correlation_key")
            or payload.get("subject_key")
            or payload.get("matched_value")
            or payload.get("scan_key")
            or payload.get("owner_key")
            or payload.get("owner_email")
            or payload.get("email")
            or payload.get("subject_ref")
            or payload.get("subject_reference")
        )
        email = None
        user_id = payload.get("customer_reference") or payload.get("subject_ref") or payload.get("subject_reference")
        hash_val = None

        if raw_ident:
            if "@" in raw_ident:
                email = raw_ident.lower()
            elif raw_ident.startswith("user_"):
                user_id = raw_ident
            elif len(raw_ident) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw_ident):
                hash_val = raw_ident.lower()

        # Inherit from trace context
        tid = payload.get("trace_id") or payload.get("requestId")
        if tid and trace_context and str(tid) in trace_context:
            t_ctx = trace_context[str(tid)]
            if not email and "email" in t_ctx:
                email = t_ctx["email"]
            if not user_id and "user_id" in t_ctx:
                user_id = t_ctx["user_id"]
            if not hash_val and "hash" in t_ctx:
                hash_val = t_ctx["hash"]

        if not res_id:
            return None

        # Check status
        http_status = str(payload.get("http_status", ""))
        result = str(payload.get("result", "")).lower()
        rows = str(payload.get("rows", ""))
        event = str(payload.get("event", "")).lower()
        detector = str(payload.get("detector", ""))

        if http_status == "404" or result in ("miss", "not_found") or rows == "0":
            state = ObservedState.ABSENT
        elif http_status == "200" or result in ("hit", "found") or rows == "1":
            state = ObservedState.PRESENT
        elif detector == "direct_identifier" or payload.get("direct_identifiers") == "1" or "pii_scan" in event or "identity_scan" in event:
            state = ObservedState.PRESENT
        elif payload.get("message_text") == "[REDACTED]":
            state = ObservedState.REDACTED
        elif "audit_record" in event and (payload.get("integrity_check") == "passed" or rows == "1"):
            state = ObservedState.PRESENT
        elif "deletion_block" in payload:
            is_blocked = str(payload["deletion_block"]).lower() == "true"
            state = ObservedState.BLOCKED if is_blocked else ObservedState.ACTIVE
        elif "restore_allowed" in payload:
            is_allowed = str(payload["restore_allowed"]).lower() == "true"
            state = ObservedState.ACTIVE if is_allowed else ObservedState.BLOCKED
        elif "enabled" in payload:
            is_en = str(payload["enabled"]).lower() == "true"
            state = ObservedState.ACTIVE if is_en else ObservedState.DISABLED
        elif "available" in payload:
            is_av = str(payload["available"]).lower() == "true"
            state = ObservedState.PRESENT if is_av else ObservedState.ABSENT
        else:
            state = ObservedState.UNKNOWN

        if state == ObservedState.UNKNOWN:
            return None

        # Normalize service
        if "account" in svc or "profile" in svc:
            sys_id = "account_service"
            cat = "USER_PROFILE"
        elif "search" in svc:
            sys_id = "search_service"
            cat = "SEARCH_INDEX_ENTRY"
        elif "support" in svc:
            sys_id = "support_platform"
            cat = "SUPPORT_MESSAGE"
        elif "analytics" in svc:
            sys_id = "analytics_platform"
            cat = "ANALYTICS_PROFILE"
        elif "connector" in svc or "integration" in svc:
            sys_id = "integration_service"
            cat = "CONNECTOR_SUBSCRIPTION"
        elif "backup" in svc:
            sys_id = "backup_service"
            cat = "BACKUP_ARCHIVE"
        elif "security" in svc or "audit" in svc:
            sys_id = "security_service"
            cat = "SECURITY_AUDIT_LOG"
        elif "export" in svc:
            sys_id = "export_service"
            cat = "USER_EXPORT"
        else:
            sys_id = svc or "account_service"
            cat = "USER_PROFILE"

        supp_idents = []
        if hash_val:
            supp_idents.append(hash_val)

        return EvidenceObservation(
            observation_id=obs_id,
            evidence_id=file_id,
            source_file=rel_path,
            source_location=f"line:{line_no}",
            extraction_method="log_json_parser",
            captured_at=manifest_captured_at,
            event_time=event_time,
            system_id=sys_id,
            resource_id=res_id,
            resource_type=cat,
            data_category=cat,
            observed_state=state,
            user_id=user_id,
            matched_identifier=email or hash_val or user_id,
            supporting_identifiers=supp_idents,
            raw_payload=payload,
            semantic_interpretation=f"Structured JSON log event: {res_id} -> {state.value}",
        )
