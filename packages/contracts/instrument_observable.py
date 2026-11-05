from __future__ import annotations

import math

_MODULE_SOURCE = "instrument_readback"
_REQUIRED_KEYS = {
    "field",
    "value",
    "unit",
    "observed_at_simulation_s",
    "quality",
    "reason",
    "uncertainty",
}


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    # Python integers are finite; converting large integers to float can overflow.
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _validate_numeric_metadata(value: object, name: str) -> None:
    if not _is_finite_number(value):
        raise ValueError(f"{name} must be a finite non-boolean number")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _validate_value(value: object, descriptor: dict) -> None:
    dtype = descriptor.get("type")
    if dtype == "number":
        if not _is_finite_number(value):
            raise ValueError("number value must be a finite non-boolean number")
        minimum = descriptor.get("minimum")
        maximum = descriptor.get("maximum")
        if minimum is not None and value < minimum:
            raise ValueError("number value below minimum")
        if maximum is not None and value > maximum:
            raise ValueError("number value above maximum")
    elif dtype == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean value must be bool")
    elif dtype == "string":
        if not isinstance(value, str) or value != "SE":
            raise ValueError("string value must be exactly SE")
    else:
        raise ValueError("unsupported descriptor type")


def _validate_quality_reason_value(quality: object, reason: object, value: object, descriptor: dict) -> None:
    if quality == "reported":
        if value is None:
            raise ValueError("reported quality requires a nonnull value")
        if reason is not None:
            raise ValueError("reported quality requires null reason")
        _validate_value(value, descriptor)
    elif quality == "stale":
        if reason != "stale":
            raise ValueError("stale quality requires reason stale")
        if value is not None:
            _validate_value(value, descriptor)
    elif quality == "unavailable":
        if value is not None:
            raise ValueError("unavailable quality requires null value")
        if not isinstance(reason, str) or reason not in {"not_exposed", "sensor_unavailable", "not_implemented"}:
            raise ValueError("unavailable quality requires an allowed reason")
    else:
        raise ValueError("unsupported quality")


def project_readbacks(records: list[dict], registry: dict) -> list[dict]:
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if not isinstance(registry, dict):
        raise ValueError("registry must be a dict")

    result: list[dict] = []
    seen: set[str] = set()

    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ValueError("registry must contain a fields list")

    descriptors: dict[str, dict] = {}
    for descriptor in fields:
        if not isinstance(descriptor, dict):
            raise ValueError("registry field descriptor must be a dict")
        field = descriptor.get("field")
        if not isinstance(field, str):
            raise ValueError("registry field descriptor must include a string field")
        descriptors[field] = descriptor

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("record must be a dict")

        keys = set(record.keys())
        if keys != _REQUIRED_KEYS:
            raise ValueError("record must contain exactly the required keys")

        field = record["field"]
        if not isinstance(field, str):
            raise ValueError("field must be a string")
        if field in seen:
            raise ValueError(f"duplicate field {field}")

        descriptor = descriptors.get(field)
        if descriptor is None:
            raise ValueError(f"unknown field {field}")

        available_on = descriptor.get("available_on")
        if not isinstance(available_on, list) or "instrument" not in available_on:
            raise ValueError(f"field {field} is not available on instrument")

        unit = record["unit"]
        if unit != descriptor.get("unit"):
            raise ValueError(f"unit mismatch for field {field}")

        observed_at = record["observed_at_simulation_s"]
        _validate_numeric_metadata(observed_at, "observed_at_simulation_s")

        uncertainty = record["uncertainty"]
        if uncertainty is not None:
            _validate_numeric_metadata(uncertainty, "uncertainty")

        quality = record["quality"]
        reason = record["reason"]
        value = record["value"]

        _validate_quality_reason_value(quality, reason, value, descriptor)

        seen.add(field)
        result.append({
            "field": field,
            "value": value,
            "unit": unit,
            "observed_at_simulation_s": observed_at,
            "quality": quality,
            "reason": reason,
            "uncertainty": uncertainty,
            "source": _MODULE_SOURCE,
        })

    return result
