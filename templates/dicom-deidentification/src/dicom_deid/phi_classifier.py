"""PHI Classifier — determines whether detected text is Protected Health Information.

Uses fuzzy matching against DICOM metadata PHI values to classify
detected burned-in text as PHI or non-PHI. Text that fuzzy-matches
a known PHI value above a configurable threshold is classified as PHI
and should be masked. Text that doesn't match any PHI value (or matches
a known safe pattern) is left unmasked.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import pydicom
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe patterns — common non-PHI text found in medical images
# ---------------------------------------------------------------------------

# Single/short tokens that are never PHI
_SAFE_TOKENS: set[str] = {
    # Laterality markers
    "l", "r", "lt", "rt", "left", "right",
    # Orientation markers
    "a", "p", "s", "i", "h", "f",
    "ap", "pa", "lat", "si", "rl",
    "ant", "post", "sup", "inf",
    # Common equipment/scan labels
    "portable", "erect", "supine", "prone",
    "axial", "coronal", "sagittal",
    # Units
    "cm", "mm", "hz", "mhz", "khz", "db", "db/cm",
    "ma", "kv", "kvp", "mas", "mgy", "msv",
    "bpm", "sec", "ms", "min",
    # Common scan parameters
    "ob", "general", "gain", "ti", "te", "tr",
    "fov", "dfov", "ww", "wl",
    # View labels
    "cc", "mlo", "lcc", "rmlo", "lmlo", "rcc",
    # Misc safe labels
    "store in progress", "cine", "freeze",
    "2d", "3d", "4d", "m-mode", "b-mode",
    "doppler", "color", "power",
}

# Regex patterns for non-PHI text
_SAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d{1,3}$"),                    # Pure short numbers (1-3 digits)
    re.compile(r"^\d+(\.\d+)?\s*(cm|mm|hz|mhz|db|ma|kv|kvp|bpm|sec|ms)$", re.I),  # Number + unit
    re.compile(r"^\d+/[+\-]?\d+/\d+/\d+$"),     # Gain patterns like 51/+1/3/4
    re.compile(r"^\d+x\d+$", re.I),              # Resolution like 512x512
    re.compile(r"^[A-Z]{1,2}\d{1,2}$"),          # Probe labels like 6C2, L12
    re.compile(r"^\d+(\.\d+)?\s*deg$", re.I),    # Degrees
    re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)$", re.I),  # Month abbreviations
    re.compile(r"^rotation\??$", re.I),           # Rotation label
    re.compile(r"^views?:?\s*\d*$", re.I),        # Views label
]


# ---------------------------------------------------------------------------
# PHI value extraction from DICOM metadata
# ---------------------------------------------------------------------------

# DICOM tags that contain PHI values to match against
_PHI_TAGS = [
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x0030),  # PatientBirthDate
    (0x0010, 0x1040),  # PatientAddress
    (0x0010, 0x2154),  # PatientTelephoneNumbers
    (0x0008, 0x0050),  # AccessionNumber
    (0x0008, 0x0080),  # InstitutionName
    (0x0008, 0x0081),  # InstitutionAddress
    (0x0008, 0x0090),  # ReferringPhysicianName
    (0x0008, 0x1050),  # PerformingPhysicianName
    (0x0008, 0x1070),  # OperatorsName
    (0x0008, 0x1010),  # StationName
    (0x0010, 0x1000),  # OtherPatientIDs
    (0x0010, 0x1001),  # OtherPatientNames
]


def _extract_phi_values(dataset: pydicom.Dataset) -> list[str]:
    """Extract all PHI string values from a DICOM dataset.

    Returns a list of normalized (lowercased, stripped) non-empty strings
    from PHI-related DICOM attributes. Multi-valued attributes and
    person name components are split into individual tokens.
    """
    values: list[str] = []

    for group, elem in _PHI_TAGS:
        tag = pydicom.tag.Tag(group, elem)
        if tag not in dataset:
            continue

        raw = dataset[tag].value
        if raw is None:
            continue

        # Handle PersonName — split into components
        raw_str = str(raw)
        if not raw_str.strip():
            continue

        # Split on common DICOM delimiters: ^, \, /
        parts = re.split(r"[\^\\\/,\s]+", raw_str)
        for part in parts:
            part = part.strip()
            if len(part) >= 2:  # Skip single chars
                values.append(part.lower())

    return values


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy comparison.

    Lowercases, strips whitespace, removes common OCR noise characters.
    """
    text = text.lower().strip()
    # Remove common punctuation that OCR might add/miss
    text = re.sub(r"[:\-_.,;'\"()\[\]{}]", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# PHI Classifier
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Result of PHI classification for a single detected text region."""
    text: str
    is_phi: bool
    matched_phi_value: str | None = None
    match_score: float = 0.0
    reason: str = ""


@dataclass
class PHIClassifier:
    """Classifies detected text as PHI or non-PHI using fuzzy matching.

    The classifier extracts PHI values from the DICOM metadata and
    compares each detected text region against them using fuzzy string
    matching. Text that closely matches a known PHI value is classified
    as PHI. Text matching safe patterns (laterality markers, units,
    equipment labels) is classified as non-PHI.

    Parameters
    ----------
    phi_match_threshold:
        Minimum fuzzy match score (0-100) to classify text as PHI.
        Default is 70, which handles common OCR errors like O→Q, S→5.
    min_text_length:
        Minimum text length to consider for PHI matching. Very short
        text (1-2 chars) is almost never PHI. Default is 3.
    """
    phi_match_threshold: float = 70.0
    min_text_length: int = 3
    _phi_values: list[str] = field(default_factory=list, repr=False)

    def load_phi_from_dataset(self, dataset: pydicom.Dataset) -> None:
        """Extract PHI values from the DICOM dataset for matching."""
        self._phi_values = _extract_phi_values(dataset)
        logger.debug("Extracted %d PHI values for matching", len(self._phi_values))

    def classify(self, text: str) -> ClassificationResult:
        """Classify a single detected text string as PHI or non-PHI.

        Returns a ClassificationResult with the classification decision,
        the matched PHI value (if any), and the match score.
        """
        normalized = _normalize_for_comparison(text)

        # Skip very short text
        if len(normalized) < self.min_text_length:
            return ClassificationResult(
                text=text, is_phi=False, reason="too_short"
            )

        # Check safe tokens (exact match after normalization)
        if normalized in _SAFE_TOKENS:
            return ClassificationResult(
                text=text, is_phi=False, reason="safe_token"
            )

        # Check safe patterns (regex)
        for pattern in _SAFE_PATTERNS:
            if pattern.match(normalized):
                return ClassificationResult(
                    text=text, is_phi=False, reason="safe_pattern"
                )

        # Fuzzy match against PHI values
        best_score = 0.0
        best_match = None

        for phi_val in self._phi_values:
            # Full ratio — good for similar-length strings
            score_full = fuzz.ratio(normalized, phi_val)

            # Partial ratio — only use when PHI value is long enough
            # to avoid false positives (e.g., "al" matching "general")
            score_partial = 0.0
            if len(phi_val) >= 4:
                score_partial = fuzz.partial_ratio(normalized, phi_val)

            # Token sort ratio — handles reordered words
            score_token = 0.0
            if len(phi_val) >= 4:
                score_token = fuzz.token_sort_ratio(normalized, phi_val)

            score = max(score_full, score_partial, score_token)

            if score > best_score:
                best_score = score
                best_match = phi_val

        if best_score >= self.phi_match_threshold:
            return ClassificationResult(
                text=text,
                is_phi=True,
                matched_phi_value=best_match,
                match_score=best_score,
                reason="phi_match",
            )

        return ClassificationResult(
            text=text, is_phi=False, match_score=best_score, reason="no_match"
        )
