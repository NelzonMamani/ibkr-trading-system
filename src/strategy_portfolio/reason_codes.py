"""Reason codes for strategy portfolio governance decisions."""

from enum import Enum


class ReasonCode(str, Enum):
    ACTIVATION_DISALLOW = "activation_disallow"
    UNIVERSE_REJECT = "universe_reject"
    DATA_QUALITY_FAIL = "data_quality_fail"
    ARBITRATION_DENY = "arbitration_deny"
    ARBITRATION_DENY_LOWER_PRIORITY = "arbitration_deny_lower_priority"
    ALLOCATION_EXHAUSTED = "allocation_exhausted"
    ALLOCATION_DISABLED = "allocation_disabled"
    RISK_VETO = "risk_veto"
    MISSING_FIELD_DEFAULT = "missing_field_default"
    MISSING_POLICY_FIELDS = "missing_policy_fields"
    MAPPING_UNSUPPORTED_OUTPUT = "mapping_unsupported_output"
