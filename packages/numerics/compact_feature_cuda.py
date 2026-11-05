import torch
import triton
import triton.language as tl
import triton.language.math as dm

__all__ = ('compact_feature_sum',)


@triton.jit
def _d(value: tl.constexpr):
    return tl.full((), value, tl.float64)


@triton.jit
def _compact_feature_kernel(
    x_ptr, y_ptr, feat_ptr, out_ptr,
    N: tl.constexpr, F: tl.constexpr,
    BLOCK_N: tl.constexpr,
):
    pid = tl.program_id(0)
    offs_n = pid * BLOCK_N + tl.arange(0, BLOCK_N)
    mask_n = offs_n < N

    x = tl.load(x_ptr + offs_n, mask=mask_n, other=0.0)
    y = tl.load(y_ptr + offs_n, mask=mask_n, other=0.0)

    z = tl.zeros([BLOCK_N], dtype=tl.float64)
    dx = tl.zeros([BLOCK_N], dtype=tl.float64)
    dy = tl.zeros([BLOCK_N], dtype=tl.float64)
    m = tl.zeros([BLOCK_N], dtype=tl.float64)

    for i in range(0, F):
        cx = tl.load(feat_ptr + i * 11 + 0)
        cy = tl.load(feat_ptr + i * 11 + 1)
        rx = tl.load(feat_ptr + i * 11 + 2)
        ry = tl.load(feat_ptr + i * 11 + 3)
        angle = tl.load(feat_ptr + i * 11 + 4)
        height = tl.load(feat_ptr + i * 11 + 5)
        contrast = tl.load(feat_ptr + i * 11 + 6)
        kind = tl.load(feat_ptr + i * 11 + 7)
        period = tl.load(feat_ptr + i * 11 + 8)
        phase = tl.load(feat_ptr + i * 11 + 9)
        step_width = tl.load(feat_ptr + i * 11 + 10)

        c = dm.cos(angle)
        s = dm.sin(angle)

        bx = dm.sqrt((rx * c) * (rx * c) + (ry * s) * (ry * s))
        by = dm.sqrt((rx * s) * (rx * s) + (ry * c) * (ry * c))

        dx_pt = x - cx
        dy_pt = y - cy

        in_bbox = (tl.abs(dx_pt) < bx) & (tl.abs(dy_pt) < by)

        u = tl.where(in_bbox, c * dx_pt + s * dy_pt, 0.)
        v = tl.where(in_bbox, -s * dx_pt + c * dy_pt, 0.)

        r = dm.sqrt((u / rx) * (u / rx) + (v / ry) * (v / ry))

        active = in_bbox & (r < 1.0)

        a = tl.where(active, 1.0 - r, 0.)
        bump = (a * a * a * a) * (4.0 * r + 1.0)

        du = -20.0 * (a * a * a) * u / (rx * rx)
        dv = -20.0 * (a * a * a) * v / (ry * ry)

        pattern = tl.full([BLOCK_N], 1., tl.float64)
        pu = tl.zeros([BLOCK_N], tl.float64)
        pv = tl.zeros([BLOCK_N], tl.float64)

        if kind == 1.0 or kind == 2.0:
            k = _d(6.283185307179586) / period
            pattern = dm.sin(k * u + phase)
            pu = k * dm.cos(k * u + phase)
            if kind == 2.0:
                old = pattern
                old_pu = pu
                pattern = old * dm.cos(_d(0.73) * k * v)
                pu = old_pu * dm.cos(_d(0.73) * k * v)
                pv = -_d(0.73) * k * old * dm.sin(_d(0.73) * k * v)
        elif kind == 3.0:
            t = dm.tanh(u / step_width)
            pattern = 0.5 * (1.0 + t)
            pu = 0.5 * (1.0 - t * t) / step_width

        bu = du * pattern + bump * pu
        bv = dv * pattern + bump * pv

        z += tl.where(active, height * bump * pattern, 0.0)
        dx += tl.where(active, height * (c * bu - s * bv), 0.0)
        dy += tl.where(active, height * (s * bu + c * bv), 0.0)
        m += tl.where(active, contrast * bump * pattern, 0.0)

    tl.store(out_ptr + 0 * N + offs_n, z, mask=mask_n)
    tl.store(out_ptr + 1 * N + offs_n, dx, mask=mask_n)
    tl.store(out_ptr + 2 * N + offs_n, dy, mask=mask_n)
    tl.store(out_ptr + 3 * N + offs_n, m, mask=mask_n)


def compact_feature_sum(x, y, features):
    if type(x) is not torch.Tensor or type(y) is not torch.Tensor or type(features) is not torch.Tensor:
        raise ValueError("inputs must be torch.Tensor")
    if x.dtype is not torch.float64 or y.dtype is not torch.float64 or features.dtype is not torch.float64:
        raise ValueError("inputs must be float64")
    if any(t.layout != torch.strided for t in (x,y,features)):
        raise ValueError('dense strided inputs required')
    if x.requires_grad or y.requires_grad or features.requires_grad:
        raise ValueError("inputs must not require grad")
    if not x.is_cuda or not y.is_cuda or not features.is_cuda:
        raise ValueError("inputs must be CUDA tensors")
    if x.device != y.device or x.device != features.device:
        raise ValueError("inputs must be on the same device")
    if x.dim() != 1 or y.dim() != 1:
        raise ValueError("x and y must be rank 1")
    if x.shape[0] != y.shape[0]:
        raise ValueError("x and y must have the same length")
    if not x.is_contiguous() or not y.is_contiguous():
        raise ValueError("x and y must be contiguous")
    if features.dim() != 2 or features.shape[1] != 11:
        raise ValueError("features must be rank 2 with shape (F, 11)")
    if not features.is_contiguous():
        raise ValueError("features must be contiguous")

    N = x.shape[0]
    F = features.shape[0]

    if not torch.isfinite(x).all() or not torch.isfinite(y).all() or not torch.isfinite(features).all():
        raise ValueError("inputs must be finite")

    if F > 0:
        rx = features[:, 2]
        ry = features[:, 3]
        period = features[:, 8]
        step_width = features[:, 10]
        kind = features[:, 7]
        if not (rx > 0).all() or not (ry > 0).all() or not (period > 0).all() or not (step_width > 0).all():
            raise ValueError("invalid row scalars")
        if not (kind == torch.floor(kind)).all():
            raise ValueError("kind must be integer-valued")
        if not ((kind >= 0) & (kind <= 3)).all():
            raise ValueError("kind must be in [0, 3]")

    if N == 0:
        return torch.empty((4, 0), dtype=torch.float64, device=x.device)

    out = torch.empty((4, N), dtype=torch.float64, device=x.device)

    if F == 0:
        out.zero_()
        return out

    BLOCK_N = 256
    grid = (triton.cdiv(N, BLOCK_N),)
    _compact_feature_kernel[grid](
        x, y, features, out,
        N=N, F=F, BLOCK_N=BLOCK_N,
        num_warps=4,
        enable_fp_fusion=False,
    )

    if not torch.isfinite(out).all():
        raise ValueError("nonfinite output")

    return out
