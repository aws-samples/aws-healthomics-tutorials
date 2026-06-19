"""Enums for DICOM de-identification actions and hash tiers."""

from enum import Enum


class Action(Enum):
    """De-identification action applied to a DICOM attribute."""

    HASH_8 = "hash_8"
    HASH_16 = "hash_16"
    HASH_24 = "hash_24"
    HASH_32 = "hash_32"
    DATE_SHIFT = "date_shift"
    TRUNCATE = "truncate"
    REMOVE = "remove"
    KEEP = "keep"


class HashTier(Enum):
    """Hash truncation length in hex characters for parameterized hash actions."""

    HASH_8 = 8
    HASH_16 = 16
    HASH_24 = 24
    HASH_32 = 32


class OverrideMode(Enum):
    """How a profile-supplied value combines with an existing tag value.

    ``REPLACE`` — discard the current value and write the supplied one.
    ``PREFIX``  — concatenate ``value + existing`` (existing kept verbatim).
    ``SUFFIX``  — concatenate ``existing + value`` (existing kept verbatim).

    For ``PREFIX``/``SUFFIX`` on a tag that is absent or empty, the
    existing value is treated as ``""`` and the tag is created (if
    absent) with just the supplied value.
    """

    REPLACE = "replace"
    PREFIX = "prefix"
    SUFFIX = "suffix"


class UnmatchedTextPolicy(Enum):
    """Policy for OCR-detected text that does not fuzzy-match any DICOM PHI value.

    ``MASK``  — treat unmatched text as PHI and mask it (safe default for
                operator-typed free text that won't appear in metadata).
    ``KEEP``  — leave unmatched text intact (only mask metadata-matched text).
    ``FAIL``  — fail the instance so a human can review.
    """

    MASK = "mask"
    KEEP = "keep"
    FAIL = "fail"
