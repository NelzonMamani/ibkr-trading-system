"""Authoritative Trading OS decision-pipeline stages and outcomes."""

from __future__ import annotations

from enum import Enum


class DecisionStage(str, Enum):
    SCAN = "SCAN"
    CONTEXT = "CONTEXT"
    STRUCTURE = "STRUCTURE"
    SETUP = "SETUP"
    CONFIRMATION = "CONFIRMATION"
    TRIGGER = "TRIGGER"
    INTENT = "INTENT"
    EXECUTION = "EXECUTION"
    FILL = "FILL"
    POSITION = "POSITION"
    EXIT = "EXIT"


CANONICAL_DECISION_PIPELINE: tuple[DecisionStage, ...] = (
    DecisionStage.SCAN,
    DecisionStage.CONTEXT,
    DecisionStage.STRUCTURE,
    DecisionStage.SETUP,
    DecisionStage.CONFIRMATION,
    DecisionStage.TRIGGER,
    DecisionStage.INTENT,
    DecisionStage.EXECUTION,
    DecisionStage.FILL,
    DecisionStage.POSITION,
    DecisionStage.EXIT,
)


class DecisionFailureClassification(str, Enum):
    DATA_BLOCKED_AT_CONTEXT = "DATA_BLOCKED_AT_CONTEXT"
    STRUCTURE_NOT_ACTIONABLE = "STRUCTURE_NOT_ACTIONABLE"
    SETUP_NOT_FOUND = "SETUP_NOT_FOUND"
    SETUP_FAILED_CONFIRMATION = "SETUP_FAILED_CONFIRMATION"
    SETUP_FOUND_BUT_NO_TRIGGER = "SETUP_FOUND_BUT_NO_TRIGGER"
    TRIGGER_FOUND_BUT_INTENT_BLOCKED = "TRIGGER_FOUND_BUT_INTENT_BLOCKED"
    FULL_PIPELINE_SUCCESS = "FULL_PIPELINE_SUCCESS"
