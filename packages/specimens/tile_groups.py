import numpy as np


def group_pairs(x, y):
    if type(x) is not np.ndarray or type(y) is not np.ndarray:
        raise ValueError("Inputs must be numpy.ndarray")
    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Inputs must be 1-dimensional")
    if x.dtype != np.int64 or y.dtype != np.int64:
        raise ValueError("Inputs must have dtype int64")
    if x.shape != y.shape:
        raise ValueError("Inputs must have equal shape")

    n = x.shape[0]
    if n == 0:
        return (
            np.empty(0, dtype=np.int64),
            np.array([0], dtype=np.int64),
            np.empty((0, 2), dtype=np.int64),
        )

    # Create a structured array view to sort lexicographically by x then y.
    # This avoids packing into a single int64 key which could overflow.
    # We use a structured dtype with two int64 fields.
    # To ensure stability and correct ordering, we sort the indices based on the structured values.
    
    # Create a structured array that references x and y.
    # We need to be careful not to mutate inputs. We create a new structured array.
    # However, creating a structured array from two separate arrays requires copying or careful view manipulation.
    # A safer approach for sorting: use np.lexsort. 
    # np.lexsort((y, x)) sorts by x first, then y. It is stable.
    # It returns indices.
    
    # np.lexsort is stable and handles int64 extremes correctly.
    # It returns an array of indices of shape (N,).
    
    # Check if inputs are read-only or strided. np.lexsort handles this fine.
    
    # Get the sorted indices
    order = np.lexsort((y, x))
    
    # Now we have the order of original indices sorted by (x, y).
    # We need to find the boundaries of groups where (x, y) is identical.
    
    # Extract the sorted x and y values
    sorted_x = x[order]
    sorted_y = y[order]
    
    # Find where the pair changes.
    # A pair changes if x changes OR y changes.
    # We can compute this by comparing adjacent elements.
    
    # For the first element, it's always a new group start.
    # For i > 0, it's a new group start if sorted_x[i] != sorted_x[i-1] or sorted_y[i] != sorted_y[i-1].
    
    if n == 1:
        starts = np.array([0, 1], dtype=np.int64)
        keys = np.array([[x[0], y[0]]], dtype=np.int64)
        return (order, starts, keys)

    # Compute change flags
    # x_changed[i] is True if sorted_x[i] != sorted_x[i-1]
    # y_changed[i] is True if sorted_y[i] != sorted_y[i-1]
    
    # We need to be careful with overflow? No, comparison is safe.
    
    x_changed = sorted_x[1:] != sorted_x[:-1]
    y_changed = sorted_y[1:] != sorted_y[:-1]
    
    # A new group starts at index i (in the sorted array) if i==0 or (x_changed[i-1] or y_changed[i-1])
    # Let's create a boolean array of length N indicating the start of a group.
    
    is_start = np.empty(n, dtype=bool)
    is_start[0] = True
    is_start[1:] = x_changed | y_changed
    
    # Find the indices where is_start is True
    start_indices = np.nonzero(is_start)[0]
    
    # The number of groups G is len(start_indices)
    g = len(start_indices)
    
    # starts array: [0, start_indices[1], ..., start_indices[g-1], N]
    # Wait, start_indices are the indices in the sorted array where a new group begins.
    # So the first group starts at 0.
    # The second group starts at start_indices[1].
    # ...
    # The last group starts at start_indices[g-1].
    # And the end is N.
    
    # So starts = [0, start_indices[1], ..., start_indices[g-1], N]
    # But start_indices[0] is always 0.
    # So starts = np.concatenate(([0], start_indices[1:], [n]))
    
    starts = np.empty(g + 1, dtype=np.int64)
    starts[0] = 0
    if g > 1:
        starts[1:g] = start_indices[1:]
    starts[g] = n
    
    # keys array: shape (G, 2)
    # For each group g, the key is (sorted_x[start_indices[g]], sorted_y[start_indices[g]])
    
    keys = np.empty((g, 2), dtype=np.int64)
    keys[:, 0] = sorted_x[start_indices]
    keys[:, 1] = sorted_y[start_indices]
    
    # Ensure outputs are C-contiguous and owned.
    # np.lexsort returns a new array.
    # starts and keys are newly allocated.
    # sorted_x and sorted_y are views/copies? x[order] creates a new array (copy) if order is not a simple slice.
    # Actually, x[order] with an integer array index creates a copy.
    # So sorted_x and sorted_y are new arrays.
    # We don't return them, so it's fine.
    
    # Check contiguity
    if not order.flags['C_CONTIGUOUS']:
        order = np.ascontiguousarray(order)
    if not starts.flags['C_CONTIGUOUS']:
        starts = np.ascontiguousarray(starts)
    if not keys.flags['C_CONTIGUOUS']:
        keys = np.ascontiguousarray(keys)

    return (order, starts, keys)
