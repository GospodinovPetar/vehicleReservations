from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def _normalize_validation_error(err: DjangoValidationError):
    # Django ValidationError can be .message_dict (field -> [errors]) or .messages (list)
    if hasattr(err, "message_dict"):
        return err.message_dict
    return {"non_field_errors": err.messages}


def custom_exception_handler(exc, context):
    """
    Maps common server-side exceptions to clean JSON responses.
    Falls back to DRF's default; if still None, returns a generic 500 with a message.
    """
    # 1) Handle Django model/form validation errors as HTTP 400
    if isinstance(exc, DjangoValidationError):
        return Response({"errors": _normalize_validation_error(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # 2) Integrity (unique constraints, FKs, etc.) -> 400 with a generic but user-friendly message
    if isinstance(exc, IntegrityError):
        return Response(
            {"errors": {"non_field_errors": ["Operation could not be completed due to a data integrity constraint."]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3) Defer to DRF's default (handles ParseError, NotAuthenticated, PermissionDenied, NotFound, etc.)
    response = exception_handler(exc, context)
    if response is not None:
        # Optionally ensure consistent envelope
        if isinstance(response.data, dict) and "detail" in response.data:
            # keep DRF's "detail" but still structured
            response.data = {"detail": response.data["detail"]}
        return response

    # 4) True unexpected error -> 500 with a safe message (no traceback)
    return Response({"detail": "Unexpected server error. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
