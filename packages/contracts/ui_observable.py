from __future__ import annotations

import math

_REQUIRED_KEYS = {
    "field",
    "value",
    "unit",
    "observed_at_simulation_s",
    "quality",
    "reason",
    "uncertainty",
}

_UNAVAILABLE_REASONS = {
    "not_exposed",
    "sensor_unavailable",
    "not_implemented",
}


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    # Python integers are finite; converting large integers to float can overflow.
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _validate_metadata_time(value: object) -> None:
    if not _is_finite_number(value):
        raise ValueError("observed_at_simulation_s must be a finite non-boolean number")
    if value < 0:
        raise ValueError("observed_at_simulation_s must be nonnegative")


def _validate_uncertainty(value: object) -> None:
    if value is None:
        return
    if not _is_finite_number(value):
        raise ValueError("uncertainty must be null or a finite non-boolean number")
    if value < 0:
        raise ValueError("uncertainty must be nonnegative")


def _validate_value(value: object, descriptor: dict) -> None:
    if value is None:
        return

    field_type = descriptor["type"]
    if field_type == "number":
        if not _is_finite_number(value):
            raise ValueError("numeric value must be a finite non-boolean number")
        minimum = descriptor["minimum"]
        maximum = descriptor["maximum"]
        if minimum is not None and value < minimum:
            raise ValueError("numeric value below minimum")
        if maximum is not None and value > maximum:
            raise ValueError("numeric value above maximum")
    elif field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean value must be bool")
    elif field_type == "string":
        if not isinstance(value, str) or value != "SE":
            raise ValueError("string value must be exactly SE")
    else:
        raise ValueError(f"unsupported descriptor type: {field_type}")


def _validate_quality_reason(quality: object, reason: object, value: object) -> None:
    if quality == "reported":
        if value is None:
            raise ValueError("reported quality requires a nonnull value")
        if reason is not None:
            raise ValueError("reported quality requires null reason")
    elif quality == "stale":
        if reason != "stale":
            raise ValueError("stale quality requires reason stale")
    elif quality == "unavailable":
        if value is not None:
            raise ValueError("unavailable quality requires null value")
        if not isinstance(reason, str) or reason not in _UNAVAILABLE_REASONS:
            raise ValueError("unavailable quality requires an allowed reason")
    else:
        raise ValueError(f"unsupported quality: {quality}")


def project_readbacks(records: list[dict], registry: dict) -> list[dict]:
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if not isinstance(registry, dict):
        raise ValueError("registry must be a dict")

    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ValueError("registry must contain a fields list")

    descriptors: dict[str, dict] = {}
    for descriptor in fields:
        if not isinstance(descriptor, dict):
            raise ValueError("registry field descriptors must be dicts")
        field = descriptor.get("field")
        if not isinstance(field, str):
            raise ValueError("registry field descriptor must include a string field")
        if field in descriptors:
            raise ValueError(f"duplicate registry field: {field}")
        descriptors[field] = descriptor

    result: list[dict] = []
    seen: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each record must be a dict")

        keys = set(record.keys())
        if keys != _REQUIRED_KEYS:
            raise ValueError("record must contain exactly the required keys")

        field = record["field"]
        if not isinstance(field, str):
            raise ValueError("field must be a string")
        if field in seen:
            raise ValueError(f"duplicate field: {field}")

        descriptor = descriptors.get(field)
        if descriptor is None:
            raise ValueError(f"unknown field: {field}")

        available_on = descriptor.get("available_on")
        if not isinstance(available_on, list) or "ui" not in available_on:
            raise ValueError(f"field not available on ui: {field}")

        unit = record["unit"]
        if unit != descriptor["unit"]:
            raise ValueError(f"unit mismatch for field: {field}")

        observed_at = record["observed_at_simulation_s"]
        _validate_metadata_time(observed_at)

        uncertainty = record["uncertainty"]
        _validate_uncertainty(uncertainty)

        quality = record["quality"]
        reason = record["reason"]
        value = record["value"]

        _validate_quality_reason(quality, reason, value)

        if value is not None:
            _validate_value(value, descriptor)

        seen.add(field)
        result.append(
            {
                "field": field,
                "value": value,
                "unit": unit,
                "observed_at_simulation_s": observed_at,
                "quality": quality,
                "reason": reason,
                "uncertainty": uncertainty,
                "source": "ui_readback",
            }
        )

    return result
