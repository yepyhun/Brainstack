"""Typed Brainstack exception taxonomy."""

from __future__ import annotations

from .reason_codes import ReasonCode


class BrainstackError(Exception):
    reason_code: ReasonCode = ReasonCode.UNCLASSIFIED


class CapabilityUnavailable(BrainstackError):
    reason_code = ReasonCode.BACKEND_UNAVAILABLE


class BackendDegraded(BrainstackError):
    reason_code = ReasonCode.BACKEND_UNAVAILABLE


class MigrationBlocked(BrainstackError):
    reason_code = ReasonCode.UNCLASSIFIED


class StoreInvariantViolation(BrainstackError):
    reason_code = ReasonCode.UNCLASSIFIED


class AuthorityBoundaryViolation(BrainstackError):
    reason_code = ReasonCode.AUTHORITY_MISMATCH


class PublicSurfaceRegression(BrainstackError):
    reason_code = ReasonCode.PUBLIC_SURFACE_PROTECTED
