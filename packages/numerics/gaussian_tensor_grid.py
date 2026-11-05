import torch

__all__ = ('gaussian_grid',)


def _validate_tensor(t, name, expected_len=None):
    if type(t) is not torch.Tensor:
        raise ValueError(f"{name} must be an exact torch.Tensor")
    if t.layout != torch.strided or t.device.type not in ('cpu', 'cuda'):
        raise ValueError(f"{name} must be dense strided")
    if t.dtype != torch.float64:
        raise ValueError(f"{name} must be float64")
    if t.requires_grad:
        raise ValueError(f"{name} must not require grad")
    if t.dim() != 1:
        raise ValueError(f"{name} must be rank 1")
    if not torch.isfinite(t).all():
        raise ValueError(f"{name} must contain only finite values")
    if expected_len is not None and t.numel() != expected_len:
        raise ValueError(f"{name} must have length {expected_len}")


def _validate_device(t, name, ref_device):
    if t.device != ref_device:
        raise ValueError(f"{name} device must match reference device")


def gaussian_grid(x, y, xx, xy, yy, nodes, weights):
    # Validate all inputs
    _validate_tensor(x, 'x')
    _validate_tensor(y, 'y')
    _validate_tensor(xx, 'xx')
    _validate_tensor(xy, 'xy')
    _validate_tensor(yy, 'yy')
    _validate_tensor(nodes, 'nodes')
    _validate_tensor(weights, 'weights')

    N = x.numel()
    K = nodes.numel()

    # Check equal lengths for x, y, xx, xy, yy
    if y.numel() != N or xx.numel() != N or xy.numel() != N or yy.numel() != N:
        raise ValueError("x, y, xx, xy, yy must have equal length")

    # Check K >= 1
    if K < 1:
        raise ValueError("nodes and weights must have length K >= 1")

    # Check weights length matches nodes
    if weights.numel() != K:
        raise ValueError("nodes and weights must have equal length")

    # Check all devices match
    ref_device = x.device
    for t, name in [(y, 'y'), (xx, 'xx'), (xy, 'xy'), (yy, 'yy'), (nodes, 'nodes'), (weights, 'weights')]:
        _validate_device(t, name, ref_device)

    # Check xx > 0 and yy > 0 for all rows
    if N > 0:
        if not (xx > 0).all():
            raise ValueError("xx must be strictly positive for all rows")
        if not (yy > 0).all():
            raise ValueError("yy must be strictly positive for all rows")

    # Check weights nonnegative
    if not (weights >= 0).all():
        raise ValueError("weights must be nonnegative")

    # Compute sum S
    S = weights.sum()
    if not torch.isfinite(S) or S <= 0:
        raise ValueError("sum of weights must be finite and strictly positive")

    # Normalize weights
    normalized = weights / S

    # Compute quadrature weights: outer product of normalized with itself
    # quadrature_weights[j] = normalized[i] * normalized[k] where j = i*K + k
    quadrature_weights = torch.outer(normalized, normalized).reshape(-1).clone()

    if N == 0:
        coordinates = torch.empty((0, K * K, 2), dtype=torch.float64, device=ref_device)
        return (coordinates, quadrature_weights)

    # Compute a, b, c
    a = torch.sqrt(xx)
    b = xy / a
    remaining = yy - b * b

    # Check a, b, remaining finite and remaining > 0
    if not torch.isfinite(a).all():
        raise ValueError("a must be finite")
    if not torch.isfinite(b).all():
        raise ValueError("b must be finite")
    if not torch.isfinite(remaining).all():
        raise ValueError("remaining must be finite")
    if not (remaining > 0).all():
        raise ValueError("remaining must be strictly positive")

    c = torch.sqrt(remaining)

    # Build coordinates
    # For each n, i, k: j = i*K + k
    # coordinates[n, j, 0] = x[n] + a[n] * nodes[i]
    # coordinates[n, j, 1] = y[n] + b[n] * nodes[i] + c[n] * nodes[k]

    # nodes shape: (K,)
    # a, b, c, x, y shape: (N,)

    # We need to create tensors of shape (N, K, K, 2)
    # For the first coordinate: x[n] + a[n] * nodes[i]
    #   x[n] -> (N, 1, 1)
    #   a[n] * nodes[i] -> (N, K, 1)
    # For the second coordinate: y[n] + b[n] * nodes[i] + c[n] * nodes[k]
    #   y[n] -> (N, 1, 1)
    #   b[n] * nodes[i] -> (N, K, 1)
    #   c[n] * nodes[k] -> (N, 1, K)

    x_exp = x.unsqueeze(1).unsqueeze(2)  # (N, 1, 1)
    y_exp = y.unsqueeze(1).unsqueeze(2)  # (N, 1, 1)
    a_exp = a.unsqueeze(1).unsqueeze(2)  # (N, 1, 1)
    b_exp = b.unsqueeze(1).unsqueeze(2)  # (N, 1, 1)
    c_exp = c.unsqueeze(1).unsqueeze(2)  # (N, 1, 1)

    nodes_i = nodes.unsqueeze(0).unsqueeze(2)  # (1, K, 1)
    nodes_k = nodes.unsqueeze(0).unsqueeze(1)  # (1, 1, K)

    coord0 = x_exp + a_exp * nodes_i  # (N, K, 1)
    coord1 = y_exp + b_exp * nodes_i + c_exp * nodes_k  # (N, K, K)

    # Expand coord0 to (N, K, K)
    coord0 = coord0.expand(N, K, K)

    # Stack to (N, K, K, 2)
    coords = torch.stack((coord0, coord1), dim=-1)

    # Reshape to (N, K*K, 2)
    coordinates = coords.reshape(N, K * K, 2)

    # Check finiteness of results
    if not torch.isfinite(coordinates).all():
        raise ValueError("computed coordinates must be finite")
    if not torch.isfinite(quadrature_weights).all():
        raise ValueError("computed quadrature weights must be finite")

    # Ensure new owning contiguous tensors
    coordinates = coordinates.contiguous().clone()
    quadrature_weights = quadrature_weights.contiguous().clone()

    return (coordinates, quadrature_weights)
