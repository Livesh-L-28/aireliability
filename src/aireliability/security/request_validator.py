"""Request validation engine for Gateway requests."""

import json
import re

from aireliability.security.models import GatewayRequest, ValidationResult

# Regex matching valid tenant/project/namespace IDs
IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
ACTION_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


class RequestValidator:
    """Validates structural constraints, size bounds, and identifiers
    on Gateway requests.
    """

    def __init__(
        self,
        max_payload_bytes: int = 1_048_576,  # 1MB limit
        max_metadata_bytes: int = 65_536,  # 64KB limit
    ) -> None:
        self.max_payload_bytes = max_payload_bytes
        self.max_metadata_bytes = max_metadata_bytes

    def validate(self, request: GatewayRequest) -> ValidationResult:
        """Validate request structure, payload bounds, and naming constraints."""
        # 1. Check Request ID
        if not request.request_id or len(request.request_id) > 128:
            return ValidationResult(
                valid=False, reason="Invalid or missing request_id."
            )

        # 2. Check Action format
        if not request.action or not ACTION_REGEX.match(request.action):
            return ValidationResult(
                valid=False, reason=f"Invalid action format: '{request.action}'."
            )

        # 3. Check Tenant ID format
        if not IDENTIFIER_REGEX.match(request.tenant_id):
            return ValidationResult(
                valid=False, reason=f"Invalid tenant_id format: '{request.tenant_id}'."
            )

        # 4. Check Project ID format
        if not IDENTIFIER_REGEX.match(request.project_id):
            return ValidationResult(
                valid=False,
                reason=f"Invalid project_id format: '{request.project_id}'.",
            )

        # 5. Check Namespace format
        if not IDENTIFIER_REGEX.match(request.namespace):
            return ValidationResult(
                valid=False, reason=f"Invalid namespace format: '{request.namespace}'."
            )

        # 6. Payload size validation
        try:
            payload_str = json.dumps(request.payload)
            if len(payload_str.encode("utf-8")) > self.max_payload_bytes:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Payload size exceeds maximum allowed "
                        f"({self.max_payload_bytes} bytes)."
                    ),
                )
        except Exception as e:
            return ValidationResult(
                valid=False, reason=f"Failed to serialize payload: {e}"
            )

        # 7. Metadata size validation
        try:
            meta_str = json.dumps(request.metadata)
            if len(meta_str.encode("utf-8")) > self.max_metadata_bytes:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Metadata size exceeds maximum allowed "
                        f"({self.max_metadata_bytes} bytes)."
                    ),
                )
        except Exception as e:
            return ValidationResult(
                valid=False, reason=f"Failed to serialize metadata: {e}"
            )

        return ValidationResult(valid=True)
