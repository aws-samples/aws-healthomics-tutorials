"""Deidentifier for DICOM metadata de-identification."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

import pydicom
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.tag import Tag

from .enums import Action, HashTier, OverrideMode
from .models import DeidentificationProfile, InstanceInfo, TagOverride

logger = logging.getLogger(__name__)


# DICOM VRs that hold human-readable strings (and where an empty-string
# value is a valid Type 2 representation of "no value"). For numeric,
# binary, or sequence VRs, assigning "" is rejected by pydicom and the
# correct "remove" semantics is to delete the tag entirely.
#
# Source: DICOM PS3.5 Table 6.2-1 (VRs and their data types).
_STRING_VRS: frozenset[str] = frozenset({
    "AE",  # Application Entity
    "AS",  # Age String (e.g. "045Y")
    "CS",  # Code String
    "DA",  # Date
    "DS",  # Decimal String — numeric VALUE but stored as a string;
           # pydicom accepts "" here.
    "DT",  # Date Time
    "IS",  # Integer String — same as DS, string-encoded numeric.
    "LO",  # Long String
    "LT",  # Long Text
    "PN",  # Person Name
    "SH",  # Short String
    "ST",  # Short Text
    "TM",  # Time
    "UC",  # Unlimited Characters
    "UI",  # Unique Identifier
    "UR",  # URI
    "UT",  # Unlimited Text
})


# DICOM PS3.5 §6.2 maximum value length per string VR (chars), used to
# right-truncate the result of a tag override. The cap reflects the
# DICOM standard, not pydicom's runtime; pydicom won't reject an
# over-length value, so without the cap we'd silently produce
# non-conformant DICOM.
#
# Multi-line note: PN's 64-char cap is per component group; this code
# treats it as a single string and caps the whole thing. That's
# operationally fine for prefix/suffix use cases and keeps the rule
# uniform. Operators who need component-aware editing should use
# ``replace`` and supply a fully-formed PN.
#
# UT/LT/ST are technically capped at 10240 / 10240 / 1024 respectively
# but pydicom enforces those caps itself when writing, so we apply
# them here as well to fail loud rather than have pydicom crop on
# write.
_VR_MAX_LENGTH: dict[str, int] = {
    "AE": 16,
    "AS": 4,
    "CS": 16,
    "DA": 8,
    "DS": 16,
    "DT": 26,
    "IS": 12,
    "LO": 64,
    "LT": 10240,
    "PN": 64,
    "SH": 16,
    "ST": 1024,
    "TM": 14,
    "UC": 2**32 - 2,
    "UI": 64,
    "UR": 2**32 - 2,
    "UT": 2**32 - 2,
}


def _empty_or_delete(dataset: Dataset, tag: Tag, element) -> None:
    """REMOVE the value of *element* in a VR-appropriate way.

    String VRs keep the tag with an empty-string value (Type 2 empty —
    DICOM-valid and preserves the structural presence of the tag). SQ
    keeps the tag with an empty list. Everything else (numeric, binary)
    has no DICOM-valid empty representation, so we delete the tag.
    """
    vr = element.VR
    if vr == "SQ":
        element.value = []
    elif vr in _STRING_VRS:
        element.value = ""
    else:
        # Numeric / binary VR: pydicom rejects "" assignment with a
        # UserWarning ("A value of type 'str' cannot be assigned to a
        # tag with VR US."). Drop the tag instead — semantically
        # equivalent to REMOVE and silent.
        del dataset[tag]


# ---------------------------------------------------------------------------
# UID skiplist prefixes — values whose first characters match any of these are
# left untouched by the VR=UI sweep.
#
#   "1.2.840.10008."  is the DICOM standard's own arc, used for Transfer
#                     Syntax UIDs, SOP Class UIDs, Implementation Class UIDs
#                     and other registry-defined values.  Hashing them would
#                     turn the file into something no parser can read.
#   "2.25."           is the ITU-T joint-iso-itu-t/uuid arc.  We use it as
#                     our own output prefix (see ``generate_uid``); skipping
#                     it makes a second deid pass a no-op (idempotent) and
#                     avoids re-hashing UIDs that another anonymizer (GDCM,
#                     CTP) already minted under the same arc.
# ---------------------------------------------------------------------------

_UID_SKIP_PREFIXES: tuple[str, ...] = ("1.2.840.10008.", "2.25.")


# ---------------------------------------------------------------------------
# Mapping from Action enum hash variants to HashTier
# ---------------------------------------------------------------------------

_ACTION_TO_HASH_TIER: dict[Action, HashTier] = {
    Action.HASH_8: HashTier.HASH_8,
    Action.HASH_16: HashTier.HASH_16,
    Action.HASH_24: HashTier.HASH_24,
    Action.HASH_32: HashTier.HASH_32,
}


def _parse_dicom_tag(tag_str: str) -> Tag:
    """Convert a DICOM tag string like ``(0010,0020)`` to a pydicom ``Tag``."""
    stripped = tag_str.strip("()")
    group_str, elem_str = stripped.split(",")
    return Tag(int(group_str, 16), int(elem_str, 16))


class Deidentifier:
    """Apply de-identification actions to DICOM metadata per profile configuration."""

    def __init__(self, profile: DeidentificationProfile) -> None:
        self._profile = profile
        self._uid_cache: dict[str, str] = {}
        self._date_offset_cache: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Helper methods (Task 4.1)
    # ------------------------------------------------------------------

    def hash_attribute(self, value: str, tier: HashTier) -> str:
        """SHA-256(salt + value) → hex → truncate to *tier* length.

        Parameters
        ----------
        value:
            The original attribute value to hash.
        tier:
            The :class:`HashTier` controlling how many hex characters to keep.

        Returns
        -------
        str
            Truncated hex digest.
        """
        digest = hashlib.sha256(
            (self._profile.salt + value).encode("utf-8")
        ).hexdigest()
        return digest[: tier.value]

    def generate_uid(self, original_uid: str) -> str:
        """Generate a de-identified DICOM UID from *original_uid*.

        Algorithm: SHA-256(salt + uid) → int → decimal string → truncate
        60 chars → prepend ``"2.25."``.  Result is at most 64 characters.
        """
        if original_uid in self._uid_cache:
            return self._uid_cache[original_uid]

        digest = hashlib.sha256(
            (self._profile.salt + original_uid).encode("utf-8")
        ).digest()
        num = int.from_bytes(digest, "big")
        decimal_str = str(num)[:59]
        uid = f"2.25.{decimal_str}"

        self._uid_cache[original_uid] = uid
        return uid

    def compute_date_shift_offset(self, patient_id: str) -> int:
        """Deterministic date-shift offset in days for *patient_id*.

        ``int.from_bytes(SHA-256(salt + patient_id)[:4], 'big') mod max_date_shift_days``
        """
        if patient_id in self._date_offset_cache:
            return self._date_offset_cache[patient_id]

        digest = hashlib.sha256(
            (self._profile.salt + patient_id).encode("utf-8")
        ).digest()
        offset = int.from_bytes(digest[:4], "big") % self._profile.max_date_shift_days

        self._date_offset_cache[patient_id] = offset
        return offset

    def shift_date(self, date_value: str, offset_days: int) -> str:
        """Shift a DICOM date string (``YYYYMMDD``) forward by *offset_days*.

        Returns the shifted date in ``YYYYMMDD`` format. Raises
        ``ValueError`` if *date_value* is not a valid DA-format string.
        Use :meth:`shift_value_for_vr` when the VR may be DA, TM, or DT.
        """
        dt = datetime.strptime(date_value[:8], "%Y%m%d")
        shifted = dt + timedelta(days=offset_days)
        return shifted.strftime("%Y%m%d")

    def shift_value_for_vr(
        self,
        value: str,
        vr: str,
        offset_days: int,
    ) -> str:
        """VR-aware date shift.

        DICOM date-related VRs each have their own format, and the same
        profile rule (action=date_shift) can land on any of them:

          * **DA** — ``YYYYMMDD``: shift the whole value by ``offset_days``.
          * **TM** — ``HHMMSS[.FFFFFF]``: a time-of-day with no date
            component. A *date* offset is meaningless here, so we
            return the value unchanged. This is the right choice for
            patient-privacy: the TM alone reveals nothing about the
            date and offsetting it would break correlation with
            adjacent DA siblings (e.g. StudyDate + StudyTime).
          * **DT** — ``YYYYMMDDHHMMSS[.FFFFFF][&ZZXX]``: combined
            date+time. Shift the leading 8 chars (the date), preserve
            the time + fractional + timezone tail verbatim.

        Unknown VRs return the value unchanged with no exception so
        a typo in profile attribute_overrides can't kill the whole
        instance — the per-attribute error path will surface the
        miss without taking down de-id.
        """
        if not value:
            return value

        if vr == "DA":
            return self.shift_date(value, offset_days)

        if vr == "TM":
            # Time-of-day doesn't carry a date; offsetting it makes
            # no sense and would desynchronise it from sibling DA tags.
            return value

        if vr == "DT":
            # DT layout: YYYYMMDDHHMMSS[.FFFFFF][&ZZXX]. The date is
            # the first 8 characters; everything after is preserved.
            if len(value) < 8:
                return value
            shifted_date = self.shift_date(value[:8], offset_days)
            return shifted_date + value[8:]

        # Unknown VR: leave it alone. The profile-level intent
        # (date_shift) doesn't translate to non-temporal VRs.
        return value

    def truncate_age(self, age_str: str) -> str:
        """Truncate a DICOM age string to the decade.

        Example: ``"045Y"`` → ``"040Y"``

        The DICOM age format is ``NNNX`` where ``NNN`` is a zero-padded
        number and ``X`` is the unit (``Y``, ``M``, ``W``, ``D``).
        """
        if len(age_str) < 2:
            return age_str
        unit = age_str[-1]
        numeric = age_str[:-1]
        try:
            val = int(numeric)
        except ValueError:
            return age_str
        truncated = (val // 10) * 10
        return f"{truncated:03d}{unit}"

    # ------------------------------------------------------------------
    # Main de-identification method (Task 4.2)
    # ------------------------------------------------------------------

    def deidentify(
        self,
        dataset: pydicom.Dataset,
        instance_info: InstanceInfo,
    ) -> pydicom.Dataset:
        """Apply all de-identification actions to *dataset* in-place.

        Processing order:
        1. Remove tags in ``drop_tags_list``
        2. Remove private tags if ``drop_private_tags`` is true
        3. Apply per-attribute actions from ``attribute_actions``
           (which already includes overrides merged by ProfileLoader)
        4. Replace Study / Series / Instance UIDs with de-identified UIDs
        """
        profile = self._profile

        # 1. Remove tags in drop_tags_list
        for tag_str in profile.drop_tags_list:
            tag = _parse_dicom_tag(tag_str)
            if tag in dataset:
                del dataset[tag]

        # 2. Handle private tags
        if profile.drop_private_tags:
            dataset.remove_private_tags()

        # 3. Compute date-shift offset once per patient
        date_offset = self.compute_date_shift_offset(instance_info.patient_id)

        # 4. Apply per-attribute actions from the merged attribute_actions dict.
        # Each tag is wrapped in try/except so one malformed value can't
        # take down the entire instance's de-id. The fallback is to
        # REMOVE the offending attribute — the safer default when we
        # can't transform it as configured. The unparseable value is
        # never logged (it could be PHI); only the tag, action, and
        # exception class are surfaced.
        for tag_str, action in profile.attribute_actions.items():
            tag = _parse_dicom_tag(tag_str)
            if tag not in dataset:
                continue

            element = dataset[tag]
            try:
                if action == Action.KEEP:
                    # Preserve unchanged
                    continue

                if action == Action.REMOVE:
                    # VR-aware REMOVE. String VRs become "" (the
                    # DICOM-canonical Type 2 empty); SQ becomes [];
                    # numeric/binary VRs are deleted because they have
                    # no valid empty-string representation. Without
                    # this distinction, pydicom emits a UserWarning
                    # for every "" assignment to a numeric VR (saw
                    # 168 occurrences on the PS3.15 profile).
                    _empty_or_delete(dataset, tag, element)
                    continue

                if action in _ACTION_TO_HASH_TIER:
                    tier = _ACTION_TO_HASH_TIER[action]
                    original_value = str(element.value)
                    element.value = self.hash_attribute(original_value, tier)
                    continue

                if action == Action.DATE_SHIFT:
                    original_value = str(element.value)
                    if original_value:
                        element.value = self.shift_value_for_vr(
                            original_value, element.VR, date_offset
                        )
                    continue

                if action == Action.TRUNCATE:
                    original_value = str(element.value)
                    if original_value:
                        element.value = self.truncate_age(original_value)
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Per-attribute %s on %s (VR=%s) failed: %s. "
                    "Falling back to REMOVE for safety.",
                    action.value if hasattr(action, "value") else action,
                    tag_str,
                    element.VR,
                    type(exc).__name__,
                )
                try:
                    _empty_or_delete(dataset, tag, element)
                except Exception as fallback_exc:  # noqa: BLE001
                    # If even VR-aware REMOVE fails (very rare; would
                    # mean a corrupted dataset), drop the tag entirely.
                    logger.warning(
                        "REMOVE fallback for %s also failed (%s); deleting tag.",
                        tag_str, type(fallback_exc).__name__,
                    )
                    try:
                        del dataset[tag]
                    except Exception:  # noqa: BLE001
                        pass

        # 5. Apply tag overrides AFTER per-attribute actions ran. Order
        # matters: a profile rule like "(0008,1030) prefix '[TRIAL] '"
        # needs to land on whatever StudyDescription came out of the
        # de-id pipeline, not on the raw PHI value. Each override is
        # wrapped in its own try/except so one bad entry can't kill the
        # rest of the instance — same posture as the action loop above.
        for override in profile.override_tag_list:
            try:
                self._apply_tag_override(dataset, override)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Tag override on %s (mode=%s) failed: %s. Skipping.",
                    override.tag, override.mode.value, type(exc).__name__,
                )

        # 6. Sweep every VR=UI element (top-level + nested in any sequence)
        # and remap its value through ``generate_uid``.  The shared cache in
        # ``self._uid_cache`` guarantees that a given source UID always maps
        # to the same de-identified UID, so cross-references — Study/Series/
        # SOP at the top level, ReferencedSOPInstanceUID inside SR/PR/RT
        # sequences, FrameOfReferenceUID across series, MediaStorage*UID in
        # the file-meta header — all reconnect to the right targets without
        # a per-tag table.  Standard registry UIDs (Transfer Syntax, SOP
        # Class, Implementation Class, …) are skipped via prefix; values
        # already minted under our own ``2.25.`` arc are skipped to make a
        # second deid pass a no-op.
        if profile.replace_uids:
            self._remap_ui_elements(dataset)
            file_meta = getattr(dataset, "file_meta", None)
            if file_meta is not None:
                self._remap_ui_elements(file_meta)

        return dataset

    # ------------------------------------------------------------------
    # VR=UI sweep
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Tag overrides
    # ------------------------------------------------------------------

    def _apply_tag_override(self, dataset: Dataset, override: TagOverride) -> None:
        """Apply a single ``TagOverride`` to *dataset* in place.

        Handles all three modes (replace / prefix / suffix), creates the
        tag if it's absent and the override mode is ``REPLACE`` (or
        prefix/suffix on an absent tag, which is equivalent to replace
        with the supplied value), and right-truncates the result to the
        VR's maximum length.

        Raises ``ValueError`` if the tag is in the dataset with a
        non-string VR — overrides are string-VR-only, but the loader
        already gates this by VR for tags that exist in the dictionary;
        an unexpected VR at runtime (e.g. private creator block) is
        surfaced rather than silently producing garbage.
        """
        tag = _parse_dicom_tag(override.tag)

        if tag in dataset:
            element = dataset[tag]
            vr = element.VR
            if vr not in _STRING_VRS:
                raise ValueError(
                    f"override on {override.tag}: tag is present with "
                    f"non-string VR {vr}"
                )
            existing = "" if element.value is None else str(element.value)
            new_value = self._combine_override(override.mode, existing, override.value)
            element.value = self._truncate_for_vr(new_value, vr)
            return

        # Tag not present — add it. We need the VR; pydicom's tag
        # dictionary supplies it for known public tags. For unknown
        # tags (private block, retired) we refuse rather than guess
        # a VR — that's a profile-authoring mistake the operator
        # should see.
        try:
            vr = pydicom.datadict.dictionary_VR(tag)
        except KeyError as exc:
            raise ValueError(
                f"override on {override.tag}: tag is not in the DICOM "
                f"dictionary, refusing to guess a VR"
            ) from exc

        if vr not in _STRING_VRS:
            raise ValueError(
                f"override on {override.tag}: dictionary VR {vr} is not "
                f"a string VR — overrides only support string values"
            )

        # Prefix/suffix on an absent tag treats existing as "" — same
        # net effect as replace with the supplied value.
        new_value = self._combine_override(override.mode, "", override.value)
        new_value = self._truncate_for_vr(new_value, vr)
        dataset.add_new(tag, vr, new_value)

    @staticmethod
    def _combine_override(mode: OverrideMode, existing: str, supplied: str) -> str:
        """Combine *existing* and *supplied* per *mode*."""
        if mode is OverrideMode.REPLACE:
            return supplied
        if mode is OverrideMode.PREFIX:
            return supplied + existing
        if mode is OverrideMode.SUFFIX:
            return existing + supplied
        # Defensive: enum exhausted above. If a future mode is added
        # without updating this branch, fall back to replace.
        return supplied

    @staticmethod
    def _truncate_for_vr(value: str, vr: str) -> str:
        """Right-truncate *value* to the standard max length for *vr*."""
        cap = _VR_MAX_LENGTH.get(vr)
        if cap is None or len(value) <= cap:
            return value
        return value[:cap]

    def _remap_ui_elements(self, dataset: Dataset) -> None:
        """Recursively rewrite every VR=UI element in *dataset*.

        Skips values matching ``_UID_SKIP_PREFIXES`` (standard registry UIDs
        and our own ``2.25.`` output).  Recurses into SQ items so cross-
        references inside sequences (SR content, RT plan refs, source-image
        sequences, etc.) remap to the same de-identified values their
        top-level counterparts received.
        """
        for element in dataset:
            if element.VR == "SQ":
                if element.value:
                    for item in element.value:
                        self._remap_ui_elements(item)
                continue

            if element.VR != "UI":
                continue

            value = element.value
            if value is None or value == "":
                continue

            if isinstance(value, MultiValue):
                element.value = [self._maybe_remap_uid(str(v)) for v in value]
            else:
                element.value = self._maybe_remap_uid(str(value))

    def _maybe_remap_uid(self, value: str) -> str:
        """Return a remapped UID, or the original if it matches the skiplist."""
        if value.startswith(_UID_SKIP_PREFIXES):
            return value
        return self.generate_uid(value)
