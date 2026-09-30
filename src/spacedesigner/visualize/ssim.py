"""SSIM on the pixels the inpainting mask is not allowed to change."""

# Annotations on Python 3.11.
from __future__ import annotations

# Array math for the Wang SSIM terms.
import numpy as np

# Gaussian windows. The editable region is filled before the filter runs.
from scipy.ndimage import gaussian_filter

# Stabilizers from Wang et al. for images scaled to [0, 1].
_C1 = (0.01) ** 2
_C2 = (0.03) ** 2


# Mean SSIM over pixels the mask marks as unchanged.
def ssim_unchanged(before: np.ndarray, after: np.ndarray, unchanged: np.ndarray) -> float | None:
    """Return SSIM on unchanged pixels, or None when that region is empty."""
    # Both images must be the same shape.
    if before.shape != after.shape:
        # A size mismatch is not a similarity.
        raise ValueError("SSIM images must have the same shape")
    # The mask is one channel.
    if unchanged.shape != before.shape[:2]:
        # Refuse a mask that does not line up.
        raise ValueError("SSIM mask must match the image height and width")
    # Pixels the composite is required to keep.
    keep = unchanged.astype(bool)
    # No unchanged pixels means the score is undefined.
    if not np.any(keep):
        # The caller records a null score.
        return None
    # Identical locked pixels score exactly 1. The inpaint is not part of this score.
    if np.array_equal(before[keep], after[keep]):
        # The lock held.
        return 1.0
    # Collapse colour to luminance in [0, 1].
    left = _gray(before)
    # Same conversion for the edited image.
    right = _gray(after)
    # Fill the editable region with the base so the window ignores the inpaint.
    right = right.copy()
    # A window that overlaps the mask then does not count the inpaint as a difference.
    right[~keep] = left[~keep]
    # Local means.
    mu_left = gaussian_filter(left, 1.5)
    # Local mean of the edited image.
    mu_right = gaussian_filter(right, 1.5)
    # Squared means.
    mu_left_sq = mu_left * mu_left
    # Squared mean of the edited image.
    mu_right_sq = mu_right * mu_right
    # Product of means.
    mu_product = mu_left * mu_right
    # Variance of the original.
    sigma_left = gaussian_filter(left * left, 1.5) - mu_left_sq
    # Variance of the edited image.
    sigma_right = gaussian_filter(right * right, 1.5) - mu_right_sq
    # Covariance.
    sigma_both = gaussian_filter(left * right, 1.5) - mu_product
    # Wang numerator.
    numerator = (2 * mu_product + _C1) * (2 * sigma_both + _C2)
    # Wang denominator.
    denominator = (mu_left_sq + mu_right_sq + _C1) * (sigma_left + sigma_right + _C2)
    # Per-pixel SSIM.
    score = numerator / denominator
    # Average over the locked pixels. The editable region was equalised above.
    return float(np.mean(score[keep]))


# Rec. 601 luminance, or the single channel when the image is already gray.
def _gray(image: np.ndarray) -> np.ndarray:
    """Return a float64 image in [0, 1]."""
    # Accept both gray and RGB uint8 renders.
    values = image.astype(np.float64)
    # Scale 8-bit images into the SSIM range.
    if values.max(initial=0.0) > 1.0:
        # 255 becomes 1.
        values = values / 255.0
    # A single channel is already luminance.
    if values.ndim == 2:
        # Return it.
        return values
    # Rec. 601 weights.
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float64)
    # One luminance plane.
    return values[:, :, :3] @ weights
