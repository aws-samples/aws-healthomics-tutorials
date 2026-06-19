"""Profile loader for DICOM de-identification configuration.

The profile is the single source of truth for de-identification policy.
There is no hidden engine baseline: the dict written to the JSON file is
exactly the dict the engine consults.  ``attribute_overrides`` carries
every tag the operator wants acted on, with each value naming a concrete
action (``hash_8`` / ``hash_16`` / ``hash_24`` / ``hash_32`` / ``date_shift``
/ ``truncate`` / ``remove`` / ``keep``).

The bundled ``profiles/ps315_basic_tcia_v1.json`` is a ready-to-use
starting point that encodes the DICOM PS3.15 Basic Application Level
Confidentiality Profile layered with TCIA's standard options.  Operators
copy it, fill in ``salt``, and adjust per-project tweaks before
submitting it as the workflow's ``deidentification_profile`` input.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .enums import Action, OverrideMode, UnmatchedTextPolicy
from .models import DeidentificationProfile, TagOverride


class ProfileValidationError(Exception):
    """Raised when the de-identification profile is invalid."""


# Valid string values for actions (used in attribute_overrides)
_VALID_ACTIONS = {a.value for a in Action}
_VALID_ACTIONS_DISPLAY = ", ".join(sorted(_VALID_ACTIONS))

# Valid string values for unmatched_text_policy
_UNMATCHED_TEXT_POLICY_STR_MAP: dict[str, UnmatchedTextPolicy] = {
    p.value: p for p in UnmatchedTextPolicy
}
_VALID_UNMATCHED_TEXT_POLICIES_DISPLAY = ", ".join(
    sorted(_UNMATCHED_TEXT_POLICY_STR_MAP.keys())
)

# Valid string values for override modes
_OVERRIDE_MODE_STR_MAP: dict[str, OverrideMode] = {
    m.value: m for m in OverrideMode
}
_VALID_OVERRIDE_MODES_DISPLAY = ", ".join(sorted(_OVERRIDE_MODE_STR_MAP.keys()))

# Regex for a valid DICOM tag format: (XXXX,XXXX) where X is a hex digit
_DICOM_TAG_PATTERN = re.compile(r"^\([0-9A-Fa-f]{4},[0-9A-Fa-f]{4}\)$")


# All keys recognized at the top level of a profile JSON. Any other key
# is rejected with ``ProfileValidationError`` rather than silently
# ignored — historically a removed field (e.g. low_confidence_threshold
# from an older release) was a footgun: profiles upgraded cleanly but
# the operator's mental model of behavior diverged from reality.
_KNOWN_PROFILE_KEYS: frozenset[str] = frozenset({
    "salt",
    "attribute_overrides",
    "drop_private_tags",
    "drop_tags_list",
    "override_tag_list",
    "max_date_shift_days",
    "enable_pixel_text_detection",
    "enable_pixel_masking",
    "mask_lossy_images",
    "replace_uids",
    "unmatched_text_policy",
    "allow_unsupported_pixel_ts",
    "inline_checkpoint_every",
    "enable_clahe",
    "clahe_clip_limit",
    "ocr_upscale_factor",
})


def _validate_profile(raw: dict) -> None:
    """Validate the raw JSON dict and raise ``ProfileValidationError`` on issues.

    Checks are ordered so that the most fundamental problems (missing salt,
    invalid actions) are caught first.
    """
    # 0. Reject unknown top-level keys. Catches stale fields from older
    # releases (e.g. removed flags) and typos that would otherwise load
    # silently and leave the operator with a wrong mental model.  Keys
    # beginning with an underscore are treated as documentation comments
    # (e.g. ``_comment``) and ignored.
    unknown = {k for k in raw if not k.startswith("_")} - _KNOWN_PROFILE_KEYS
    if unknown:
        keys = ", ".join(sorted(unknown))
        raise ProfileValidationError(
            f"Unknown profile field(s): {keys}. "
            f"Recognized fields: {', '.join(sorted(_KNOWN_PROFILE_KEYS))}."
        )

    # 1. Missing salt
    if "salt" not in raw:
        raise ProfileValidationError(
            "Missing required field 'salt': a salt string is required for deterministic de-identification."
        )

    # 2. Invalid actions in attribute_overrides
    overrides = raw.get("attribute_overrides", {})
    if not isinstance(overrides, dict):
        raise ProfileValidationError(
            "Field 'attribute_overrides' must be a JSON object mapping DICOM tags to actions."
        )
    for tag, action_str in overrides.items():
        if not isinstance(tag, str) or not _DICOM_TAG_PATTERN.match(tag):
            raise ProfileValidationError(
                f"Invalid DICOM tag format '{tag}' in attribute_overrides: "
                "expected format '(XXXX,XXXX)' where X is a hexadecimal digit."
            )
        if action_str not in _VALID_ACTIONS:
            raise ProfileValidationError(
                f"Invalid action '{action_str}' for tag '{tag}' in attribute_overrides: "
                f"must be one of {_VALID_ACTIONS_DISPLAY}."
            )

    # 3-iii. clahe_clip_limit (optional, must be positive number when set)
    if "clahe_clip_limit" in raw:
        ccl = raw["clahe_clip_limit"]
        if isinstance(ccl, bool) or not isinstance(ccl, (int, float)) or ccl <= 0:
            raise ProfileValidationError(
                f"Invalid clahe_clip_limit '{ccl}': must be a positive number."
            )

    # 3-iv. ocr_upscale_factor (optional, must be positive int when set)
    if "ocr_upscale_factor" in raw:
        ouf = raw["ocr_upscale_factor"]
        if isinstance(ouf, bool) or not isinstance(ouf, int) or ouf < 1:
            raise ProfileValidationError(
                f"Invalid ocr_upscale_factor '{ouf}': must be a positive integer (1 = disabled)."
            )

    # 3-v. inline_checkpoint_every (optional, must be non-negative int)
    if "inline_checkpoint_every" in raw:
        ice = raw["inline_checkpoint_every"]
        if isinstance(ice, bool) or not isinstance(ice, int) or ice < 0:
            raise ProfileValidationError(
                f"Invalid inline_checkpoint_every '{ice}': must be a non-negative integer (0 = disabled)."
            )

    # 4. unmatched_text_policy enum check
    if "unmatched_text_policy" in raw:
        utp = raw["unmatched_text_policy"]
        if utp not in _UNMATCHED_TEXT_POLICY_STR_MAP:
            raise ProfileValidationError(
                f"Invalid unmatched_text_policy '{utp}': must be one of "
                f"{_VALID_UNMATCHED_TEXT_POLICIES_DISPLAY}."
            )

    # 5. Invalid tag format in drop_tags_list
    drop_tags = raw.get("drop_tags_list", [])
    if not isinstance(drop_tags, list):
        raise ProfileValidationError(
            "Field 'drop_tags_list' must be a JSON array of DICOM tag strings."
        )
    for tag in drop_tags:
        if not isinstance(tag, str) or not _DICOM_TAG_PATTERN.match(tag):
            raise ProfileValidationError(
                f"Invalid DICOM tag format '{tag}' in drop_tags_list: "
                "expected format '(XXXX,XXXX)' where X is a hexadecimal digit."
            )

    # 6. override_tag_list — list of {tag, value, mode?} objects
    override_list = raw.get("override_tag_list", [])
    if not isinstance(override_list, list):
        raise ProfileValidationError(
            "Field 'override_tag_list' must be a JSON array of "
            "{tag, value, mode?} objects."
        )
    for idx, entry in enumerate(override_list):
        if not isinstance(entry, dict):
            raise ProfileValidationError(
                f"override_tag_list[{idx}] must be an object with "
                "'tag', 'value', and optional 'mode' fields."
            )
        unknown = set(entry) - {"tag", "value", "mode"}
        if unknown:
            raise ProfileValidationError(
                f"override_tag_list[{idx}]: unknown field(s) "
                f"{sorted(unknown)}. Allowed: tag, value, mode."
            )
        tag = entry.get("tag")
        if not isinstance(tag, str) or not _DICOM_TAG_PATTERN.match(tag):
            raise ProfileValidationError(
                f"override_tag_list[{idx}]: invalid 'tag' value '{tag}'. "
                "Expected format '(XXXX,XXXX)' where X is a hexadecimal digit."
            )
        value = entry.get("value")
        if not isinstance(value, str):
            raise ProfileValidationError(
                f"override_tag_list[{idx}] (tag {tag}): 'value' must be a string."
            )
        mode = entry.get("mode", OverrideMode.REPLACE.value)
        if mode not in _OVERRIDE_MODE_STR_MAP:
            raise ProfileValidationError(
                f"override_tag_list[{idx}] (tag {tag}): invalid mode '{mode}'. "
                f"Must be one of {_VALID_OVERRIDE_MODES_DISPLAY}."
            )


class ProfileLoader:
    """Load a JSON de-identification profile from the local filesystem."""

    def load(self, path: Path) -> DeidentificationProfile:
        """Parse *path* and return a fully-populated ``DeidentificationProfile``.

        The profile JSON is the single source of truth: ``attribute_overrides``
        becomes the engine's per-tag action table verbatim.  No baseline is
        injected — tags absent from the profile are passed through unchanged
        (modulo ``drop_private_tags`` and the VR=UI sweep, which are global
        engine behaviors not encoded per-tag).

        Raises ``ProfileValidationError`` for any invalid input.
        """
        # --- Parse JSON ---
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, IOError) as exc:
            raise ProfileValidationError(
                f"Failed to read profile file '{path}': {exc}"
            ) from exc

        try:
            raw: dict = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProfileValidationError(
                f"Malformed JSON in profile file '{path}': {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ProfileValidationError(
                f"Profile file '{path}' must contain a JSON object at the top level."
            )

        # --- Validate ---
        _validate_profile(raw)

        # --- Extract fields (validation guarantees these are safe) ---
        salt: str = raw["salt"]

        # Optional fields with defaults
        # Defaults below MUST stay in sync with the dataclass defaults
        # in models.DeidentificationProfile. Both reflect the
        # production-grade settings in profiles/ps315_basic_tcia_v1.json
        # so that a profile omitting these fields gets the same
        # behaviour whether the loader runs or the dataclass is
        # constructed directly.
        max_date_shift_days: int = raw.get("max_date_shift_days", 365)
        drop_private_tags: bool = raw.get("drop_private_tags", True)
        drop_tags_list: list[str] = raw.get("drop_tags_list", [])
        enable_pixel_text_detection: bool = raw.get("enable_pixel_text_detection", True)
        enable_pixel_masking: bool = raw.get("enable_pixel_masking", True)
        mask_lossy_images: bool = raw.get("mask_lossy_images", True)
        replace_uids: bool = raw.get("replace_uids", True)
        unmatched_text_policy = _UNMATCHED_TEXT_POLICY_STR_MAP[
            raw.get("unmatched_text_policy", UnmatchedTextPolicy.MASK.value)
        ]
        allow_unsupported_pixel_ts: bool = raw.get("allow_unsupported_pixel_ts", False)
        inline_checkpoint_every: int = raw.get("inline_checkpoint_every", 50)
        enable_clahe: bool = raw.get("enable_clahe", True)
        clahe_clip_limit: float = float(raw.get("clahe_clip_limit", 2.0))
        ocr_upscale_factor: int = int(raw.get("ocr_upscale_factor", 2))

        # Attribute actions: read straight from the JSON.  No baseline.
        attribute_overrides: dict[str, Action] = {}
        for tag, action_str in raw.get("attribute_overrides", {}).items():
            attribute_overrides[tag] = Action(action_str)
        attribute_actions = dict(attribute_overrides)

        override_tag_list: list[TagOverride] = []
        for entry in raw.get("override_tag_list", []):
            override_tag_list.append(
                TagOverride(
                    tag=entry["tag"],
                    value=entry["value"],
                    mode=_OVERRIDE_MODE_STR_MAP[
                        entry.get("mode", OverrideMode.REPLACE.value)
                    ],
                )
            )

        return DeidentificationProfile(
            salt=salt,
            attribute_actions=attribute_actions,
            attribute_overrides=attribute_overrides,
            drop_private_tags=drop_private_tags,
            drop_tags_list=drop_tags_list,
            override_tag_list=override_tag_list,
            max_date_shift_days=max_date_shift_days,
            enable_pixel_text_detection=enable_pixel_text_detection,
            enable_pixel_masking=enable_pixel_masking,
            mask_lossy_images=mask_lossy_images,
            replace_uids=replace_uids,
            unmatched_text_policy=unmatched_text_policy,
            allow_unsupported_pixel_ts=allow_unsupported_pixel_ts,
            inline_checkpoint_every=inline_checkpoint_every,
            enable_clahe=enable_clahe,
            clahe_clip_limit=clahe_clip_limit,
            ocr_upscale_factor=ocr_upscale_factor,
        )
