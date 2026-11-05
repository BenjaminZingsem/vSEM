from dataclasses import dataclass
from bisect import bisect_right


def _validate_coord(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be int or float")
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            raise ValueError(f"{name} must be finite")
    else:
        try:
            fv = float(value)
        except (OverflowError, ValueError):
            raise ValueError(f"{name} must be finite and representable")
        if fv != fv or fv in (float('inf'), float('-inf')):
            raise ValueError(f"{name} must be finite")
        if int(fv) != value:
            raise ValueError(f"{name} precision loss")


def _validate_ordinal(value):
    if type(value) is not int:
        raise ValueError("ordinal must be int")
    if value < 0:
        raise ValueError("ordinal must be nonnegative")


@dataclass(frozen=True)
class BoundsIndex:
    _records: tuple
    _x_order: tuple
    _y_order: tuple

    def point(self, x, y):
        _validate_coord(x, "x")
        _validate_coord(y, "y")
        x_key = float(x)
        y_key = float(y)
        x_idx = bisect_right(self._x_order, (x_key, float('inf')))
        y_idx = bisect_right(self._y_order, (y_key, float('inf')))
        if x_idx <= y_idx:
            order, limit = self._x_order, x_idx
        else:
            order, limit = self._y_order, y_idx
        candidates = set(order[i][1] for i in range(limit))
        result = []
        for pos in sorted(candidates):
            rec = self._records[pos]
            if rec[1] <= x <= rec[3] and rec[2] <= y <= rec[4]:
                result.append(rec[0])
        return tuple(result)

    def rectangle(self, xmin, ymin, xmax, ymax):
        _validate_coord(xmin, "xmin")
        _validate_coord(ymin, "ymin")
        _validate_coord(xmax, "xmax")
        _validate_coord(ymax, "ymax")
        if xmin > xmax:
            raise ValueError("xmin must be <= xmax")
        if ymin > ymax:
            raise ValueError("ymin must be <= ymax")
        x_key = float(xmax)
        y_key = float(ymax)
        x_idx = bisect_right(self._x_order, (x_key, float('inf')))
        y_idx = bisect_right(self._y_order, (y_key, float('inf')))
        if x_idx <= y_idx:
            order, limit = self._x_order, x_idx
        else:
            order, limit = self._y_order, y_idx
        candidates = set(order[i][1] for i in range(limit))
        result = []
        for pos in sorted(candidates):
            rec = self._records[pos]
            if rec[1] <= xmax and rec[3] >= xmin and rec[2] <= ymax and rec[4] >= ymin:
                result.append(rec[0])
        return tuple(result)


def build_index(records):
    if type(records) is not tuple:
        raise ValueError("records must be a tuple")
    seen_ordinals = set()
    validated = []
    for rec in records:
        if type(rec) is not tuple or len(rec) != 5:
            raise ValueError("each record must be a 5-tuple")
        ordinal, xmin, ymin, xmax, ymax = rec
        _validate_ordinal(ordinal)
        if ordinal in seen_ordinals:
            raise ValueError("duplicate ordinal")
        seen_ordinals.add(ordinal)
        _validate_coord(xmin, "xmin")
        _validate_coord(ymin, "ymin")
        _validate_coord(xmax, "xmax")
        _validate_coord(ymax, "ymax")
        if xmin > xmax:
            raise ValueError("xmin must be <= xmax")
        if ymin > ymax:
            raise ValueError("ymin must be <= ymax")
        validated.append((ordinal, xmin, ymin, xmax, ymax))
    records_tuple = tuple(validated)
    x_order = sorted(((float(r[1]), i) for i, r in enumerate(records_tuple)), key=lambda t: (t[0], t[1]))
    y_order = sorted(((float(r[2]), i) for i, r in enumerate(records_tuple)), key=lambda t: (t[0], t[1]))
    return BoundsIndex(records_tuple, tuple(x_order), tuple(y_order))
