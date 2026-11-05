import torch
import triton
import triton.language as tl

P = 2147483647

@triton.jit(do_not_specialize=[5])
def _counter_kernel(
    A_ptr, B_ptr, R_ptr, S_ptr, Out_ptr,
    N, order, s0, s1, s2,
    BLOCK_SIZE: tl.constexpr,
):
    pid = tl.program_id(0)
    offs = pid.to(tl.int64) * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE).to(tl.int64)
    N = N.to(tl.int64)
    mask = offs < N

    a = tl.load(A_ptr + offs, mask=mask, other=0).to(tl.int64)
    b = tl.load(B_ptr + offs, mask=mask, other=0).to(tl.int64)
    r = tl.load(R_ptr + offs, mask=mask, other=0).to(tl.int64)
    s = tl.load(S_ptr + offs, mask=mask, other=0).to(tl.int64)

    a_mod = a % P
    a_mod = tl.where(a_mod < 0, a_mod + P, a_mod)
    b_mod = b % P
    b_mod = tl.where(b_mod < 0, b_mod + P, b_mod)
    r_mod = r % P
    r_mod = tl.where(r_mod < 0, r_mod + P, r_mod)
    s_mod = s % P
    s_mod = tl.where(s_mod < 0, s_mod + P, s_mod)

    mix_ab = (((a_mod ^ s0) * 104729 + (b_mod ^ s1) * 130363 + (order + 1) * 155921 + s2) % P)
    h = (mix_ab * mix_ab + 48271 * mix_ab + s2) % P

    for j in range(8):
        h = (h * 48271 + (j + 1) * 1031) % P
        h = ((h ^ (h >> 13)) * 69621) % P
        tl.store(Out_ptr + (j * N + offs), h.to(tl.int32), mask=mask)

    mix_rs = (((r_mod ^ s0) * 104729 + (s_mod ^ s1) * 130363 + (8 + 1) * 155921 + s2) % P)
    h_rs = (mix_rs * mix_rs + 48271 * mix_rs + s2) % P
    tl.store(Out_ptr + (8 * N + offs), h_rs.to(tl.int32), mask=mask)

def counter_parameter_table(A, B, R, S, *, order, seeds):
    values=(A,B,R,S)
    for t in values:
        if (type(t) is not torch.Tensor or t.layout!=torch.strided or
            t.dtype!=torch.int64 or t.ndim!=1 or t.requires_grad or
            t.device.type!='cuda' or not t.is_contiguous()):
            raise ValueError('exact same-device contiguous CUDA int64 vectors required')
    if any(t.device!=A.device or t.shape!=A.shape for t in values):
        raise ValueError('matching input device and shape required')
    if type(order) is not int or not 0<=order<=4095:
        raise ValueError('exact order in0..4095 required')
    if type(seeds) is not tuple or len(seeds)!=3 or any(type(v) is not int or not 0<=v<P for v in seeds):
        raise ValueError('exact tuple of three bounded integer seeds required')
    n=A.numel();out=torch.empty((9,n),dtype=torch.int32,device=A.device)
    if n:
        _counter_kernel[(triton.cdiv(n,256),)](A,B,R,S,out,n,order,*seeds,BLOCK_SIZE=256)
    return out
