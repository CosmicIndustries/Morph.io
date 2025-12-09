"""
dsp helpers
"""
import numpy as np

def ensure_listable(arr):
    if isinstance(arr, np.ndarray):
        return arr.astype(float).tolist()
    return arr

