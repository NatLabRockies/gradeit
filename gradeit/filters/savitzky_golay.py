from typing import Sequence, Union

import numpy as np


def savgol_filter(
    x: Union[Sequence[float], np.ndarray], window_length: int, polyorder: int = 3
) -> np.ndarray:
    """Apply a Savitzky-Golay filter to a 1-D signal.

    Parameters:
        x: the signal to smooth.
        window_length: the (odd) length of the filter window.
        polyorder: the order of the polynomial fit within each window.

    Returns:
        The smoothed signal as a float64 array the same length as ``x``.

    Uses interpolated values at both ends of the signal.
    """
    x = np.asarray(x, dtype=np.float64)

    if window_length % 2 == 0:
        raise ValueError("window_length must be odd")
    if window_length > x.size:
        raise ValueError("window_length must be <= the size of x for mode='interp'")
    if polyorder >= window_length:
        raise ValueError("polyorder must be less than window_length")

    half = window_length // 2

    # Build coefficients for the center of each window.
    positions = np.arange(-half, half + 1)
    design = np.vander(positions, polyorder + 1, increasing=True)
    coeffs = np.linalg.pinv(design)[0]

    # Smooth interior points.
    smoothed = np.convolve(x, coeffs[::-1], mode="same")

    # Fit a polynomial at each end.
    local_idx = np.arange(window_length)
    left_fit = np.polynomial.polynomial.polyfit(local_idx, x[:window_length], polyorder)
    smoothed[:half] = np.polynomial.polynomial.polyval(local_idx[:half], left_fit)

    right_fit = np.polynomial.polynomial.polyfit(local_idx, x[-window_length:], polyorder)
    smoothed[-half:] = np.polynomial.polynomial.polyval(
        local_idx[window_length - half :], right_fit
    )

    return smoothed
