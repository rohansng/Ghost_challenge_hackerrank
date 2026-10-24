"""
Evidence Normalizer
Orchestrates modality-specific extraction across all evidence files and system activity.
Builds an inverted index for fast, deterministic retrieval of evidence by user identifier.
"""

import os
import csv
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

from code.evidence_models import EvidenceObservation, ObservedState
from code.loaders import normalize_email, normalize_phone, parse_iso_datetime
from code.extractors.sql_extractor import SqlExtractor
from code.extractors.json_extractor import JsonExtractor
from code.extractors.text_extractor import TextExtractor
from code.extractors.log_extractor import LogExtractor
from code.extractors.pdf_extractor import PdfExtractor
from code.extractors.image_extractor import ImageExtractor


class EvidenceNormalizer:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.manifest: Dict[str, Dict[str, Any]] = {}
        self.observations: List[EvidenceObservation] = []
        
        # Indexes for deterministic retrieval
        self.obs_by_user_id: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        self.obs_by_email: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        self.obs_by_phone: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        self.obs_by_hash: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        self.obs_by_resource_id: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        self.obs_by_evidence_id: Dict[str, List[EvidenceObservation]] = defaultdict(list)

    def load_and_extract_all(self) -> int:
        manifest_path = os.path.join(self.dataset_dir, "evidence_files.csv")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest not found at {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.manifest[row["file_path"]] = row

        # Initialize extractors
        sql_ext = SqlExtractor(self.manifest)
        json_ext = JsonExtractor(self.manifest)
        text_ext = TextExtractor(self.manifest)
        log_ext = LogExtractor(self.manifest)
        pdf_ext = PdfExtractor(self.manifest)
        img_ext = ImageExtractor(self.manifest)

        extracted: List[EvidenceObservation] = []

        for rel_path, meta in self.manifest.items():
            full_path = os.path.join(self.dataset_dir, rel_path)
            if not os.path.exists(full_path):
                continue

            ext = os.path.splitext(full_path)[1].lower()
            file_obs: List[EvidenceObservation] = []

            if ext == ".sql":
                file_obs = sql_ext.extract_from_file(full_path, rel_path)
            elif ext == ".json":
                file_obs = json_ext.extract_from_file(full_path, rel_path)
            elif ext == ".txt":
                file_obs = text_ext.extract_from_file(full_path, rel_path)
            elif ext == ".log":
                file_obs = log_ext.extract_from_file(full_path, rel_path)
            elif ext == ".pdf":
                file_obs = pdf_ext.extract_from_file(full_path, rel_path)
            elif ext == ".png":
                file_obs = img_ext.extract_from_file(full_path, rel_path)

            extracted.extend(file_obs)

        # Ingest system activity as observations
        activity_obs = self._extract_system_activity_observations()
        extracted.extend(activity_obs)

        self.observations = extracted
        self._build_indexes()
        return len(self.observations)

    def _extract_system_activity_observations(self) -> List[EvidenceObservation]:
        activity_path = os.path.join(self.dataset_dir, "system_activity.csv")
        if not os.path.exists(activity_path):
            return []

        obs_list = []
        with open(activity_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                act_id = row["activity_id"]
                ts = parse_iso_datetime(row["event_time"])
                ev_type = row["event_type"]
                src_sys = row["source_system"]
                tgt_sys = row["target_system"]
                res_id = row["resource_id"]
                result = row["reported_result"]
                details = row["details"]

                state = ObservedState.UNKNOWN
                user_id = None
                matched_ident = None
                supp_idents = []

                # Extract identity linkage from details (e.g. LINK_RESOURCE_IDENTITY)
                uid_m = re.search(r'\b(user_\d+)\b', details)
                if uid_m:
                    user_id = uid_m.group(1)

                email_m = re.search(r'\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b', details)
                if email_m:
                    matched_ident = email_m.group(1).lower()

                # Extract secondary / downstream resource mentions
                downstream_m = re.search(r'downstream resource (\w+)', details)
                if downstream_m:
                    supp_idents.append(downstream_m.group(1))

                # Infer data category and operational state
                data_cat = ev_type
                if "DATA_FLOW" in ev_type or "CONNECTOR" in ev_type or res_id.startswith("data_flow_"):
                    data_cat = "CONNECTOR_SUBSCRIPTION"
                    if ev_type == "CHECK_DATA_FLOW":
                        state = ObservedState.ACTIVE if ("enabled" in details.lower() or result == "SUCCESS") else ObservedState.DISABLED
                    elif ev_type == "DISABLE_DATA_FLOW":
                        state = ObservedState.DISABLED if result == "SUCCESS" else ObservedState.ACTIVE
                    else:
                        state = ObservedState.ACTIVE
                elif "RESTORE" in ev_type or "BACKUP" in ev_type or res_id.startswith("backup_"):
                    data_cat = "BACKUP_ARCHIVE"
                    if ev_type == "CHECK_RESTORE_ACCESS":
                        state = ObservedState.ACTIVE if ("restored" in details.lower() or result == "SUCCESS") else ObservedState.BLOCKED
                    elif ev_type == "BLOCK_RESTORE":
                        state = ObservedState.BLOCKED if result == "SUCCESS" else ObservedState.ACTIVE
                    else:
                        state = ObservedState.ACTIVE
                elif res_id.startswith("account_"):
                    data_cat = "USER_PROFILE"
                    if ev_type in ("DELETE_RECORD", "DELETE"):
                        state = ObservedState.ABSENT if result == "SUCCESS" else ObservedState.PRESENT
                elif res_id.startswith("search_"):
                    data_cat = "SEARCH_INDEX_ENTRY"
                    if ev_type in ("DELETE_RECORD", "DELETE"):
                        state = ObservedState.ABSENT if result == "SUCCESS" else ObservedState.PRESENT
                elif res_id.startswith("analytics_"):
                    data_cat = "ANALYTICS_PROFILE"
                    if ev_type in ("ANONYMIZE_RECORD", "ANONYMIZE"):
                        state = ObservedState.ANONYMIZED if result == "SUCCESS" else ObservedState.PRESENT
                elif res_id.startswith("cache_"):
                    data_cat = "CACHE_ENTRY"
                elif res_id.startswith("export_"):
                    data_cat = "USER_EXPORT"
                elif res_id.startswith("support_"):
                    data_cat = "SUPPORT_MESSAGE"
                    if ev_type in ("REDACT_RECORD", "REDACT"):
                        state = ObservedState.REDACTED if result == "SUCCESS" else ObservedState.PRESENT
                elif res_id.startswith("audit_record_"):
                    data_cat = "SECURITY_AUDIT_LOG"
                else:
                    if ev_type in ("DELETE_RECORD", "DELETE"):
                        state = ObservedState.ABSENT if result == "SUCCESS" else ObservedState.PRESENT
                    elif ev_type in ("ANONYMIZE_RECORD", "ANONYMIZE"):
                        state = ObservedState.ANONYMIZED if result == "SUCCESS" else ObservedState.PRESENT
                    elif ev_type in ("REDACT_RECORD", "REDACT"):
                        state = ObservedState.REDACTED if result == "SUCCESS" else ObservedState.PRESENT
                    elif ev_type in ("RETAIN_RECORD", "INDEX_RECORD", "CREATE_EXPORT", "SYNC_RECORD", "UPDATE_RECORD"):
                        state = ObservedState.PRESENT

                obs = EvidenceObservation(
                    observation_id=f"activity_{act_id}",
                    evidence_id=act_id,
                    source_file="dataset/system_activity.csv",
                    source_location=f"activity_id:{act_id}",
                    extraction_method="system_activity_stream",
                    captured_at=ts,
                    event_time=ts,
                    system_id=tgt_sys or src_sys,
                    resource_id=res_id,
                    resource_type=data_cat,
                    data_category=data_cat,
                    observed_state=state,
                    user_id=user_id,
                    matched_identifier=matched_ident,
                    supporting_identifiers=supp_idents,
                    raw_payload=row,
                    semantic_interpretation=f"Global system activity event: {ev_type} -> {result}",
                )
                obs_list.append(obs)

        return obs_list


    def _build_indexes(self) -> None:
        self.obs_by_user_id.clear()
        self.obs_by_email.clear()
        self.obs_by_phone.clear()
        self.obs_by_hash.clear()
        self.obs_by_resource_id.clear()
        self.obs_by_evidence_id.clear()

        for obs in self.observations:
            if obs.user_id:
                self.obs_by_user_id[obs.user_id].append(obs)
            if obs.matched_identifier:
                clean_email = normalize_email(obs.matched_identifier)
                if "@" in clean_email:
                    self.obs_by_email[clean_email].append(obs)
                elif clean_email.startswith("user_"):
                    self.obs_by_user_id[clean_email].append(obs)

            for supp in obs.supporting_identifiers:
                if "@" in supp:
                    self.obs_by_email[normalize_email(supp)].append(obs)
                elif any(c.isdigit() for c in supp) and len(supp) > 6:
                    self.obs_by_phone[normalize_phone(supp)].append(obs)

            if obs.resource_id:
                self.obs_by_resource_id[obs.resource_id].append(obs)
            if obs.evidence_id:
                self.obs_by_evidence_id[obs.evidence_id].append(obs)

    def get_observations_for_subject(
        self,
        user_id: Optional[str],
        emails: Set[str],
        phones: Set[str] = None,
        hashes: Set[str] = None,
    ) -> List[EvidenceObservation]:
        """Deterministically retrieves all observations linked to the subject without contamination."""
        matched: Dict[str, EvidenceObservation] = {}

        if user_id and user_id in self.obs_by_user_id:
            for obs in self.obs_by_user_id[user_id]:
                matched[obs.observation_id] = obs

        for e in emails:
            norm_e = normalize_email(e)
            if norm_e in self.obs_by_email:
                for obs in self.obs_by_email[norm_e]:
                    matched[obs.observation_id] = obs

        if phones:
            for p in phones:
                norm_p = normalize_phone(p)
                if norm_p in self.obs_by_phone:
                    for obs in self.obs_by_phone[norm_p]:
                        matched[obs.observation_id] = obs

        if hashes:
            for h in hashes:
                clean_h = h.strip().lower()
                if clean_h in self.obs_by_hash:
                    for obs in self.obs_by_hash[clean_h]:
                        matched[obs.observation_id] = obs

        # Return sorted deterministically by event_time, then observation_id
        return sorted(
            matched.values(),
            key=lambda o: (o.event_time or datetime.min, o.observation_id),
        )
