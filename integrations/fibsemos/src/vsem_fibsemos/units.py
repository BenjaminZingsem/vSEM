import math


def _is_exact_number(value):
    """Check if value is exactly int or float (not bool or subclass)."""
    return type(value) in (int, float)


def _is_finite_number(value):
    """Check if value is a finite int or float."""
    if not _is_exact_number(value):
        return False
    if isinstance(value, int):
        return True
    return math.isfinite(value)


def current_to_pa(value):
    """Convert amperes to picoamperes per uncalibrated public vSEM API representability rules.

    Accepts exact built-in int or float (no bool or subclasses) representing finite amperes.
    Computes value * 1e12 and validates that the result is within 1e-9 pA of an integer
    in the range 1..1000 pA. Returns the integer picoampere value.
    Raises ValueError for all invalid inputs.
    """
    if not _is_exact_number(value):
        raise ValueError("value must be exact int or float")
    if isinstance(value, int):
        # Huge ints: check if value * 1e12 is representable and in range
        # For int, value * 1e12 is exact. We need 1 <= value*1e12 <= 1000
        # So value must be in [1e-12, 1e-9] range, but value is int, so only value=0 possible in that range
        # Actually for int, value*1e12 is an integer. We need 1 <= value*1e12 <= 1000
        # Since value is int, value*1e12 is divisible by 1e12, so the only way is if value*1e12 is between 1 and 1000
        # But 1e12 > 1000, so no int value works except possibly very small fractions, but int can't be fraction
        # So all ints are invalid
        raise ValueError("int value cannot produce valid pA in range 1..1000")

    if not math.isfinite(value):
        raise ValueError("value must be finite")

    pa = value * 1e12

    if not math.isfinite(pa):
        raise ValueError("result not finite")

    # Check binary representation error within 1e-9 pA of nearest integer
    nearest = round(pa)
    if abs(pa - nearest) > 1e-9:
        raise ValueError("pA value not within 1e-9 of integer")

    # Ensure nearest is in 1..1000
    if nearest < 1 or nearest > 1000:
        raise ValueError("nearest integer out of range 1..1000")

    return int(nearest)


def pa_to_current(value):
    """Convert picoamperes to amperes per uncalibrated public vSEM API representability rules.

    Accepts exact built-in int in range 1..1000. Returns amperes as float.
    Raises ValueError for all invalid inputs.
    """
    if type(value) is not int:
        raise ValueError("value must be exact int")
    if value < 1 or value > 1000:
        raise ValueError("value must be in range 1..1000")
    return value * 1e-12


def dwell_to_ns(value):
    """Convert seconds to nanoseconds per uncalibrated public vSEM API representability rules.

    Accepts exact built-in int or float (no bool or subclasses) representing finite seconds.
    The value must be representable as exactly 20000, 100000, or 1000000 nanoseconds
    within absolute 1e-6 ns rounding error. Returns the integer nanosecond value.
    Raises ValueError for all invalid inputs.
    """
    if not _is_exact_number(value):
        raise ValueError("value must be exact int or float")
    if isinstance(value, int):
        # For int, value * 1e9 must be exactly one of 20000, 100000, 1000000
        # So value must be 20000/1e9, 100000/1e9, or 1000000/1e9
        # These are not integers, so no int value works
        raise ValueError("int value cannot produce valid ns in allowed set")

    if not math.isfinite(value):
        raise ValueError("value must be finite")

    ns = value * 1e9

    if not math.isfinite(ns):
        raise ValueError("result not finite")

    allowed = (20000, 100000, 1000000)
    for target in allowed:
        if abs(ns - target) <= 1e-6:
            return target

    raise ValueError("ns value not within 1e-6 of allowed set")


def ns_to_dwell(value):
    """Convert nanoseconds to seconds per uncalibrated public vSEM API representability rules.

    Accepts exact built-in int in the set {20000, 100000, 1000000}. Returns seconds as float.
    Raises ValueError for all invalid inputs.
    """
    if type(value) is not int:
        raise ValueError("value must be exact int")
    if value not in (20000, 100000, 1000000):
        raise ValueError("value must be in set {20000, 100000, 1000000}")
    return value * 1e-9


def resolution(width, height):
    """Validate raster resolution per uncalibrated public vSEM API representability rules.

    Accepts exact built-in ints (no bool) for width and height. Both must be equal
    and in the set {64, 128, 256, 512, 1024}. Returns tuple (width, height).
    Raises ValueError for all invalid inputs.
    """
    if type(width) is not int or type(height) is not int:
        raise ValueError("width and height must be exact ints")
    allowed = (64, 128, 256, 512, 1024)
    if width not in allowed or height not in allowed:
        raise ValueError("width and height must be in set {64, 128, 256, 512, 1024}")
    if width != height:
        raise ValueError("width and height must be equal")
    return (width, height)


def hfw(value):
    """Validate horizontal field width in metres per uncalibrated public vSEM API representability rules.

    Accepts exact built-in int or float (no bool or subclasses) representing finite metres
    in the closed interval [1e-7, 0.005]. Returns the value as float.
    Raises ValueError for all invalid inputs.
    """
    if not _is_exact_number(value):
        raise ValueError("value must be exact int or float")
    if isinstance(value, int):
        # For int, check if it's in [1e-7, 0.005]
        # 1e-7 = 0.0000001, 0.005 = 0.005
        # No integer is in this range except possibly 0, but 0 < 1e-7
        raise ValueError("int value cannot be in range [1e-7, 0.005]")

    if not math.isfinite(value):
        raise ValueError("value must be finite")

    if value < 1e-7 or value > 0.005:
        raise ValueError("value out of range [1e-7, 0.005]")

    return float(value)
