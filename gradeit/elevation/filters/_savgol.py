"""A dependency-free Savitzky-Golay smoothing filter.

This reproduces ``scipy.signal.savgol_filter(x, window_length, polyorder)`` with
its default arguments (``deriv=0``, ``delta=1.0``, ``mode="interp"``) so the
package does not need scipy at runtime. The implementation is intentionally
small: the interior is a single correlation with precomputed coefficients and
the edges are fit with a local polynomial, matching scipy's ``"interp"`` mode.
"""

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

    The behavior matches ``scipy.signal.savgol_filter`` with default arguments,
    including the ``mode="interp"`` boundary handling, so the validation rules
    below mirror scipy's.
    """
    x = np.asarray(x, dtype=np.float64)

    if window_length % 2 == 0:
        raise ValueError("window_length must be odd")
    if window_length > x.size:
        raise ValueError("window_length must be <= the size of x for mode='interp'")
    if polyorder >= window_length:
        raise ValueError("polyorder must be less than window_length")

    half = window_length // 2

    # Savitzky-Golay coefficients: least-squares fit of a degree-`polyorder`
    # polynomial over the window positions, read out at the center (deriv=0).
    positions = np.arange(-half, half + 1)
    design = np.vander(positions, polyorder + 1, increasing=True)
    coeffs = np.linalg.pinv(design)[0]

    # Interior points: correlate the (symmetric) coefficients with the signal.
    # `np.convolve` flips its kernel, so reverse the coefficients to correlate.
    smoothed = np.convolve(x, coeffs[::-1], mode="same")

    # Edges (mode="interp"): fit one polynomial to the first/last `window_length`
    # samples and evaluate it at the boundary positions the convolution got wrong.
    local_idx = np.arange(window_length)
    left_fit = np.polynomial.polynomial.polyfit(local_idx, x[:window_length], polyorder)
    smoothed[:half] = np.polynomial.polynomial.polyval(local_idx[:half], left_fit)

    right_fit = np.polynomial.polynomial.polyfit(local_idx, x[-window_length:], polyorder)
    smoothed[-half:] = np.polynomial.polynomial.polyval(
        local_idx[window_length - half :], right_fit
    )

    return smoothed
