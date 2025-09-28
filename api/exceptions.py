from __future__ import annotations

from typing import Any, Dict, List, Union

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def _normalize_validation_error(
    err: DjangoValidationError,
) -> Dict[str, Union[List[str], Any]]:
    if hasattr(err, "message_dict") and isinstance(getattr(err, "message_dict"), dict):
        return err.message_dict
    messages = getattr(err, "messages", None)
    if messages is None:
        messages = ["Invalid input."]
    return {"non_field_errors": list(messages)}


def custom_exception_handler(exc: Exception, context: Dict[str, Any]) -> Response:
    if isinstance(exc, DjangoValidationError):
        normalized = _normalize_validation_error(exc)
        return Response({"errors": normalized}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, IntegrityError):
        return Response(
            {
                "errors": {
                    "non_field_errors": [
                        "Operation could not be completed due to a data integrity constraint."
                    ]
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(response.data, dict):
            if "detail" in response.data:
                detail_value = response.data.get("detail")
                response.data = {"detail": detail_value}
        return response

    return Response(
        {"detail": "Unexpected server error. Please try again later."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
