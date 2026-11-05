"""Private finite-support FFT layout; no change to material/probe equations."""


def compact_axis_extent(low, high):
    if type(low) is not int or type(high) is not int or low > high:
        raise ValueError('Ordered exact integer source support required')
    # Same fixed128-cell anchor as the accepted reference. Select an even
    # 2/3/5-smooth length containing both REAL source halo endpoints. Unlike
    # rounding only to powers of two,a tiny extent increase need not quadruple
    # a 2D convolution. No wraparound source node is sampled by an admitted ray.
    anchor = ((low+high)//256)*128
    needed = max(2*(anchor-low), 2*(high-anchor+1), 2)
    best = 2
    while best < needed:
        best *= 2
    a = 2
    while a <= best:
        b = a
        while b <= best:
            c = b
            while c < needed:
                c *= 5
            if c < best:
                best = c
            b *= 3
        a *= 2
    start = anchor-best//2
    if start > low or start+best-1 < high:
        raise ArithmeticError('Finite source support not contained')
    return start, best
