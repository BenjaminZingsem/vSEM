import torch

__all__ = ('valid_convolve2d',)


def _validate_tensor(t, name):
    if not isinstance(t, torch.Tensor):
        raise ValueError(f'{name} must be a torch.Tensor')
    if type(t) is not torch.Tensor:
        raise ValueError(f'{name} must be an exact torch.Tensor, not a subclass')
    if t.layout != torch.strided or t.device.type not in ('cpu', 'cuda'):
        raise ValueError(f'{name} must be dense strided on cpu or cuda')
    if t.is_sparse or t.is_quantized or t.is_meta:
        raise ValueError(f'{name} has unsupported tensor type')
    if t.is_complex():
        raise ValueError(f'{name} must be real-valued')
    if t.dtype != torch.float64:
        raise ValueError(f'{name} must be float64')
    if t.requires_grad:
        raise ValueError(f'{name} must have requires_grad False')
    if t.dim() != 3:
        raise ValueError(f'{name} must have rank 3')
    if not torch.isfinite(t).all():
        raise ValueError(f'{name} must contain only finite values')


def _validate_fft_shape(fft_shape, h_extent, w_extent):
    if fft_shape is None:
        return (h_extent, w_extent)
    if type(fft_shape) is not tuple:
        raise ValueError('fft_shape must be a tuple of two ints')
    if len(fft_shape) != 2:
        raise ValueError('fft_shape must have exactly two elements')
    for i, v in enumerate(fft_shape):
        if type(v) is not int:
            raise ValueError('fft_shape elements must be exact Python ints')
        if v < 1:
            raise ValueError('fft_shape elements must be >= 1')
    if fft_shape[0] < h_extent:
        raise ValueError('fft_shape[0] must be >= H + Kh - 1')
    if fft_shape[1] < w_extent:
        raise ValueError('fft_shape[1] must be >= W + Kw - 1')
    return fft_shape


def valid_convolve2d(scenes, kernels, fft_shape=None):
    _validate_tensor(scenes, 'scenes')
    _validate_tensor(kernels, 'kernels')

    if scenes.device != kernels.device:
        raise ValueError('scenes and kernels must be on the same device')

    B, H, W = scenes.shape
    K, Kh, Kw = kernels.shape

    if B < 1 or H < 1 or W < 1:
        raise ValueError('scenes dimensions must be >= 1')
    if K not in (1, B):
        raise ValueError('kernels batch K must be 1 or equal to scenes batch B')
    if Kh < 1 or Kh > H:
        raise ValueError('kernel height Kh must satisfy 1 <= Kh <= H')
    if Kw < 1 or Kw > W:
        raise ValueError('kernel width Kw must satisfy 1 <= Kw <= W')

    h_extent = H + Kh - 1
    w_extent = W + Kw - 1
    s = _validate_fft_shape(fft_shape, h_extent, w_extent)

    A = torch.fft.rfft2(scenes, s=s, dim=(-2, -1), norm='backward')
    Bfft = torch.fft.rfft2(kernels, s=s, dim=(-2, -1), norm='backward')
    full = torch.fft.irfft2(A * Bfft, s=s, dim=(-2, -1), norm='backward')

    out = full[:, Kh - 1:H, Kw - 1:W]

    if not torch.isfinite(out).all():
        raise ValueError('calculated valid output contains nonfinite values')

    return out.clone(memory_format=torch.contiguous_format)