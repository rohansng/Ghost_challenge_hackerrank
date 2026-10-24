"""
intent_classifier.py - Deterministic Request Intent Classifier.
Determines whether request_text authorizes deletion or represents a non-deletion action
(e.g., access, portability, rectification, marketing opt-out, login help).
"""

import re
from typing import Tuple
from code.models import RequestType


class IntentClassifier:
    """Classifies user request text into DELETION vs non-deletion categories."""

    # Phrases explicitly negating deletion or requesting account retention (evaluated FIRST)
    NEGATIVE_INTENT_PATTERNS = [
        (r"\bleave\s+the\s+account\s+active\b", RequestType.RECTIFICATION_REQUEST, "User requested profile update while leaving account active"),
        (r"\bnot\s+asking\s+for\s+deletion\b", RequestType.MARKETING_OPT_OUT, "User explicitly requested marketing opt-out, not deletion"),
        (r"\bkeep\s+the\s+account\s+as\s+it\s+is\b", RequestType.PORTABILITY_REQUEST, "User requested data download while keeping account"),
        (r"\bdo\s+not\s+close\s+the\s+account\b", RequestType.ACCOUNT_ASSISTANCE, "User requested login reset and instructed not to close account"),
        (r"\bwithout\s+removing\s+any\s+of\s+my\s+records\b", RequestType.RECTIFICATION_REQUEST, "User requested name correction without record removal"),
        (r"\bmarketing\s+lists?\s+only\b", RequestType.MARKETING_OPT_OUT, "User requested removal from marketing lists only"),
        (r"\bnot\s+a\s+request\s+to\s+erase\b", RequestType.ACCESS_REQUEST, "Subject access request: explicitly not an erasure request"),
        (r"\bleave\s+my\s+profile\b", RequestType.ACCESS_REQUEST, "User requested invoices while leaving profile and history in place"),
        (r"\bcontinue\s+using\s+the\s+service\b", RequestType.RECTIFICATION_REQUEST, "User requested email change to continue using service"),
        (r"\bdon'?t\s+delete\s+or\s+change\s+anything\b", RequestType.ACCESS_REQUEST, "Subject access request: instructed not to delete anything"),
    ]

    # Multilingual deletion affirmation patterns
    DELETION_PATTERNS = [
        # English: delete / deleted / deletion, erase / erased / erasure, remove / removed / removal, close / closed / closure
        r"\bdelet\w*",
        r"\beras\w*",
        r"\bremov\w*",
        r"\bclos(?:e|ed|ing|ure)\b",
        r"\bde-identif\w*",
        r"\bwipe\w*",
        r"\bpurge\w*",
        r"\bforgotten\b",
        r"\bprofile\s+is\s+gone\b",
        r"\bcannot\s+identify\s+me\b",
        # French
        r"\bsuppression\b",
        r"\bsupprim\w*",
        # Spanish
        r"\beliminaci[óo]n\b",
        r"\belimin\w*",
        r"\bborr\w*",
        # Portuguese
        r"\bexclus[ãa]o\b",
        r"\bexclu\w*",
        # Japanese
        r"削除",
        r"消去",
        # Korean
        r"삭제",
        r"해지",
        r"탈퇴",
    ]

    @classmethod
    def classify(cls, request_text: str) -> Tuple[bool, RequestType, str]:
        """
        Analyzes the request text.
        Returns:
            (is_deletion_authorized: bool, request_type: RequestType, rationale: str)
        """
        if not request_text or not request_text.strip():
            return False, RequestType.UNKNOWN, "Empty request text"

        text_lower = request_text.lower()

        # Step 1: Check explicit negative intent / non-deletion override patterns FIRST
        for pattern, req_type, rationale in cls.NEGATIVE_INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return False, req_type, rationale

        # Step 2: Check for affirmative deletion keywords
        for pattern in cls.DELETION_PATTERNS:
            if re.search(pattern, text_lower):
                return True, RequestType.DELETION, "Explicit account or personal data deletion authorized"

        # Step 3: Default fallback for ambiguous text
        return False, RequestType.UNKNOWN, "No authorized deletion intent detected"
