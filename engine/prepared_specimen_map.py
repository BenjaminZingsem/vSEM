"""Private exact native-field preparation; no actor, image or public route.

The old analytic/interpolated source stays immutable. This separately identified
variant changes indexing and storage only, preserving each interpolation operation.
Prepared tiles are pinned; outside that area uses the original lazy tile store.
"""
import math
from pathlib import Path
import numpy as np
from .human_specimen_map import (NativeWorldMap, TILE_CELLS, available_memory_bytes,
                                canonical, digest, strict_record)
from .human_alignment_specimen import HumanAlignmentSpecimen
from .multiscale_alignment_specimen import MultiscaleAlignmentSpecimen


def _coordinates(value):
    def contains_boolean(item):
        return isinstance(item, (bool, np.bool_)) or isinstance(item, (tuple, list)) and any(
            contains_boolean(v) for v in item)
    if contains_boolean(value):
        raise ValueError('Boolean map coordinates forbidden')
    original = np.asarray(value)
    if original.dtype.kind not in 'fiu':
        raise ValueError('Exact real map coordinates required')
    result = np.asarray(original, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError('Finite native map coordinates required')
    return result


class PreparedWorldMap(NativeWorldMap):
    def __init__(self, *, specimen=None, spacing_m=1.25e-9, cache_bytes=None, directory=None):
        # The base constructor still validates its supported immutable source.
        base = HumanAlignmentSpecimen(seed=specimen.seed) if type(specimen) is MultiscaleAlignmentSpecimen else specimen
        super().__init__(specimen=base, spacing_m=spacing_m, cache_bytes=cache_bytes)
        if type(specimen) is MultiscaleAlignmentSpecimen:
            self.specimen = specimen
        self.prepared_tiles = {}
        self.prepared_bytes = 0
        self.prepared_rectangle = None
        self._preparation_started = False
        self.initial_budget = self.budget
        self.identity = dict(self.identity)
        self.identity['preparation'] = 'vsem.private.prepared-native-world.v1'
        folder = Path(__file__).resolve().parent
        self.identity['source'] = dict(self.identity['source'])
        self.identity['source']['prepared_specimen_map.py'] = digest(Path(__file__).read_bytes())
        self.identity['specimen_kind'] = type(self.specimen).__name__
        self.identity['source']['multiscale_alignment_specimen.py'] = digest(
            (folder / 'multiscale_alignment_specimen.py').read_bytes())
        self.identity['source']['packages/specimens/tile_groups.py'] = digest(
            (folder.parent / 'packages/specimens/tile_groups.py').read_bytes())
        self.identity_digest = digest(canonical(self.identity))
        self.directory = None if directory is None else Path(directory).resolve()
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            manifest = self.directory / 'identity.json'
            if manifest.exists():
                if strict_record(manifest) != self.identity:
                    raise ValueError('Persistent prepared map identity differs')
            else:
                with manifest.open('xb') as stream:
                    stream.write(canonical(self.identity) + b'\n')

    def _tile(self, key):
        if key in self.prepared_tiles:
            return self.prepared_tiles[key]
        return super()._tile(key)

    def _lattice(self, values):
        grid = values / self.spacing
        lower = np.floor(grid)
        if np.any(lower < -self.max_grid_index) or np.any(lower + 1 > self.max_grid_index):
            raise ValueError('Native map interpolation support outside source domain')
        lower = lower.astype(np.int64)
        return lower, grid - lower

    def prepare_bounds(self, xmin, ymin, xmax, ymax):
        """Pin a CLOSED private rectangle including both interpolation neighbors.

        Exactly one startup preparation; all keys/capacity are admitted before any
        tile work. No arbitrary tile limit or silent cropping/resolution change.
        Existing persistence remains identity/hash checked and never overwritten.
        """
        if self._preparation_started:
            raise ValueError('Initial prepared rectangle is immutable')
        values = (xmin, ymin, xmax, ymax)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Finite builtin rectangle coordinates required')
        if xmin > xmax or ymin > ymax:
            raise ValueError('Ordered prepared rectangle required')
        ix, _ = self._lattice(np.array([xmin, xmax], dtype=np.float64))
        iy, _ = self._lattice(np.array([ymin, ymax], dtype=np.float64))
        tx0, tx1 = int(ix[0] // TILE_CELLS), int(ix[1] // TILE_CELLS)
        ty0, ty1 = int(iy[0] // TILE_CELLS), int(iy[1] // TILE_CELLS)
        count = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
        required = count * self.tile_bytes
        if required + self.tile_bytes > self.initial_budget:
            raise MemoryError('Measured map allowance cannot retain the whole prepared area')
        if required + self.tile_bytes * 3 > available_memory_bytes():
            raise MemoryError('Actual available memory cannot admit prepared area')
        self._preparation_started = True
        # Reserve the already admitted area progressively; original _tile keeps
        # enough LRU allowance for external demand. Failure never claims readiness.
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                key = (tx, ty)
                tile = self._tile(key)
                if key in self.cache:
                    self.cache.pop(key)
                    self.resident_bytes -= self.tile_bytes
                self.prepared_tiles[key] = tile
                self.prepared_bytes += self.tile_bytes
                self.budget = self.initial_budget - self.prepared_bytes
        self.prepared_rectangle = tuple(float(v) for v in values)
        return {'tile_count': count, 'pinned_bytes': self.prepared_bytes,
                'bounds_m': list(self.prepared_rectangle), 'identity_digest': self.identity_digest}

    def surface_arrays(self, x_m, y_m):
        from packages.specimens.tile_groups import group_pairs
        x, y = np.broadcast_arrays(_coordinates(x_m), _coordinates(y_m))
        ix, fx = self._lattice(x)
        iy, fy = self._lattice(y)
        a, b = (ix % TILE_CELLS).reshape(-1), (iy % TILE_CELLS).reshape(-1)
        u, v = fx.reshape(-1), fy.reshape(-1)
        order, starts, keys = group_pairs((ix // TILE_CELLS).reshape(-1),
                                          (iy // TILE_CELLS).reshape(-1))
        result = np.empty((4, x.size), dtype=np.float64)
        for number, key in enumerate(keys):
            ids = order[starts[number]:starts[number + 1]]
            tile = self._tile((int(key[0]), int(key[1])))
            aa, bb, uu, vv = a[ids], b[ids], u[ids], v[ids]
            result[:, ids] = ((1-uu)*(1-vv)*tile[:, bb, aa] + uu*(1-vv)*tile[:, bb, aa+1] +
                             (1-uu)*vv*tile[:, bb+1, aa] + uu*vv*tile[:, bb+1, aa+1])
        return tuple(result[i].reshape(x.shape) for i in range(4))

    def surface_grid(self, x_axis_m, y_axis_m):
        """Cartesian query without allocating/sorting a whole coordinate mesh.

        Axes may be descending, repeated, strided or scrambled. Selection changes
        only indexing: four-term binary64 bilinear arithmetic matches the oracle.
        """
        x, y = _coordinates(x_axis_m), _coordinates(y_axis_m)
        if x.ndim != 1 or y.ndim != 1:
            raise ValueError('One-dimensional Cartesian map axes required')
        ix, fx = self._lattice(x)
        iy, fy = self._lattice(y)
        required = 4 * len(x) * len(y) * 8
        if required * 2 + self.tile_bytes * 3 > available_memory_bytes():
            raise MemoryError('Actual available memory cannot admit Cartesian field query')
        result = np.empty((4, len(y), len(x)), dtype=np.float64)
        tx, ty = ix // TILE_CELLS, iy // TILE_CELLS
        ax, ay = ix % TILE_CELLS, iy % TILE_CELLS
        # Only 1D axes are grouped; no G-by-N full-field masks or coordinate sort.
        xs = [(int(key), np.flatnonzero(tx == key)) for key in np.unique(tx)]
        ys = [(int(key), np.flatnonzero(ty == key)) for key in np.unique(ty)]
        for kx, columns in xs:
            a, u = ax[columns], fx[columns]
            for ky, rows in ys:
                b, v = ay[rows, None], fy[rows, None]
                tile = self._tile((kx, ky))
                result[:, rows[:, None], columns] = (
                    (1-u)*(1-v)*tile[:, b, a] + u*(1-v)*tile[:, b, a+1] +
                    (1-u)*v*tile[:, b+1, a] + u*v*tile[:, b+1, a+1])
        return tuple(result[i] for i in range(4))
