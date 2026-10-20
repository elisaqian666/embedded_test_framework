"""Color-sensitive tests for aligned 8-bit sRGB images, using CIEDE2000."""

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps
from skimage.color import deltaE_ciede2000, rgb2hsv, rgb2lab
from skimage.measure import label, regionprops

ImageSource = str | Path | Image.Image | np.ndarray


@dataclass(frozen=True)
class ColorRegion:
    """A connected color patch; bbox uses full-image (left, top, right, bottom)."""

    color: str
    bbox: tuple[int, int, int, int]
    pixel_count: int


@dataclass(frozen=True)
class ColorComparison:
    """Statistics include only selected pixels; mask is ROI-sized, white = failure."""

    mean_delta_e: float
    max_delta_e: float
    p95_delta_e: float
    matched_fraction: float
    pixel_count: int
    mismatch_mask: Image.Image

    def assert_match(self, min_matched_fraction: float = 1.0) -> None:
        """Fail a test if too many selected pixels exceed the color tolerance."""
        _number(min_matched_fraction, "min_matched_fraction", maximum=1)
        if self.matched_fraction < min_matched_fraction:
            raise AssertionError(
                f"Color match {self.matched_fraction:.2%} < {min_matched_fraction:.2%}; "
                f"Delta E: mean={self.mean_delta_e:.3f}, p95={self.p95_delta_e:.3f}, max={self.max_delta_e:.3f}"
            )


def _number(value: float, name: str, *, maximum: float = math.inf) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be a finite number in [0, {maximum}]")


class ImageRecognitionHelper:
    """Compare image colors without resizing, aligning, or normalizing away defects.

    Untagged images and uint8 RGB arrays are assumed sRGB. Embedded ICC profiles
    are converted to sRGB. Transparent images and raw/16-bit modes are rejected.
    ROI is (left, top, right, bottom), with right/bottom excluded. An optional
    boolean mask uses full-image coordinates; True selects a pixel for testing.
    """

    def find_color_regions(
        self,
        image: ImageSource,
        color: str,
        *,
        min_area: int = 20,
        min_saturation: float = 0.35,
        min_value: float = 0.2,
        hue_range: tuple[float, float] | None = None,
        roi: tuple[int, int, int, int] | None = None,
        mask: np.ndarray | None = None,
    ) -> list[ColorRegion]:
        """Locate red/green/blue patches using HSV, largest first; absent colors return [].

        Hue endpoints are inclusive degrees in [0, 360]; start > end wraps at red.
        Defaults: red 345..15, green 75..165, blue 195..255. Saturation/value
        thresholds use [0, 1]. Four-connected pixels form a patch; min_area counts
        matching pixels, not bounding-box area. ROI/mask clip patches before labeling.
        """
        ranges = {"red": (345, 15), "green": (75, 165), "blue": (195, 255)}
        if not isinstance(color, str) or color not in ranges:
            raise ValueError("color must be red, green, or blue")
        if type(min_area) is not int or min_area < 1:
            raise ValueError("min_area must be a positive integer")
        _number(min_saturation, "min_saturation", maximum=1)
        _number(min_value, "min_value", maximum=1)
        hue_range = ranges[color] if hue_range is None else hue_range
        if not isinstance(hue_range, (tuple, list)) or len(hue_range) != 2:
            raise ValueError("hue_range must contain two degree values")
        start, end = hue_range
        _number(start, "hue start", maximum=360)
        _number(end, "hue end", maximum=360)
        rgb = self._rgb(image)
        region, selected = self._selection(rgb.shape, roi, mask)
        hsv = rgb2hsv(rgb[region])
        hue, saturation, value = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
        hue_match = (hue >= start) & (hue <= end) if start <= end else (hue >= start) | (hue <= end)
        matches = selected & hue_match & (saturation >= min_saturation) & (value >= min_value)
        # Achromatic/black pixels have undefined hue and must never become colored regions.
        matches &= (saturation > 0) & (value > 0)
        regions = []
        for patch in regionprops(label(matches, connectivity=1)):
            if patch.area < min_area:
                continue
            top, left, bottom, right = patch.bbox
            x, y = region[1].start, region[0].start
            regions.append(ColorRegion(color, (left + x, top + y, right + x, bottom + y), int(patch.area)))
        return sorted(regions, key=lambda patch: patch.pixel_count, reverse=True)

    @staticmethod
    def _rgb(source: ImageSource) -> np.ndarray:
        if isinstance(source, np.ndarray):
            if source.dtype != np.uint8 or source.ndim != 3 or source.shape[2] != 3 or 0 in source.shape:
                raise ValueError("Image array must be non-empty uint8 RGB with shape (height, width, 3)")
            return source.copy()
        if isinstance(source, (str, Path)):
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
        elif isinstance(source, Image.Image):
            image = ImageOps.exif_transpose(source)
        else:
            raise TypeError("Image must be a path, PIL image, or uint8 RGB array")
        if image.mode not in {"RGB", "RGBA", "P"} or min(image.size) == 0:
            raise ValueError("Only non-empty 8-bit RGB, opaque RGBA, or palette images are supported")
        if image.convert("RGBA").getchannel("A").getextrema() != (255, 255):
            raise ValueError("Composite transparent images onto the intended background before comparison")
        profile = image.info.get("icc_profile")
        image = image.convert("RGB")
        if profile:
            image = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                outputMode="RGB",
            )
        return np.array(image)

    @staticmethod
    def _selection(shape: tuple, roi: tuple[int, int, int, int] | None, mask: np.ndarray | None) -> tuple:
        height, width = shape[:2]
        if roi is None:
            roi = (0, 0, width, height)
        if not isinstance(roi, (tuple, list)) or len(roi) != 4 or any(type(v) is not int for v in roi):
            raise ValueError("ROI must contain four integer coordinates")
        left, top, right, bottom = roi
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("ROI must be non-empty and inside the image")
        region = (slice(top, bottom), slice(left, right))
        if mask is None:
            selected = np.ones((bottom - top, right - left), dtype=bool)
        else:
            if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != (height, width):
                raise ValueError("Mask must be a boolean array with the full image height and width")
            selected = mask[region]
        if not selected.any():
            raise ValueError("At least one pixel must be selected")
        return region, selected

    @staticmethod
    def _compare(actual: np.ndarray, expected: np.ndarray, selected: np.ndarray, tolerance: float) -> ColorComparison:
        _number(tolerance, "delta_e_tolerance")
        # Only selected pixels enter color conversion, keeping excluded overlays out of statistics.
        differences = deltaE_ciede2000(rgb2lab(expected[selected]), rgb2lab(actual[selected]))
        failures = differences > tolerance
        mask = np.zeros(selected.shape, dtype=np.uint8)
        mask[selected] = failures.astype(np.uint8) * 255
        return ColorComparison(
            mean_delta_e=float(differences.mean()),
            max_delta_e=float(differences.max()),
            p95_delta_e=float(np.percentile(differences, 95)),
            matched_fraction=float((~failures).mean()),
            pixel_count=int(differences.size),
            mismatch_mask=Image.fromarray(mask),
        )

    def compare(
        self,
        actual: ImageSource,
        reference: ImageSource,
        *,
        delta_e_tolerance: float,
        roi: tuple[int, int, int, int] | None = None,
        mask: np.ndarray | None = None,
    ) -> ColorComparison:
        """Compare corresponding pixels; tolerance is inclusive and has no product-specific default."""
        actual_rgb, reference_rgb = self._rgb(actual), self._rgb(reference)
        if actual_rgb.shape != reference_rgb.shape:
            raise ValueError("Images must have identical dimensions and already be aligned")
        region, selected = self._selection(actual_rgb.shape, roi, mask)
        return self._compare(actual_rgb[region], reference_rgb[region], selected, delta_e_tolerance)

    def match_color(
        self,
        image: ImageSource,
        expected_rgb: tuple[int, int, int],
        *,
        delta_e_tolerance: float,
        roi: tuple[int, int, int, int] | None = None,
        mask: np.ndarray | None = None,
    ) -> ColorComparison:
        """Measure the fraction matching one sRGB color, for palette/color-patch tests."""
        if (
            not isinstance(expected_rgb, (tuple, list))
            or len(expected_rgb) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in expected_rgb)
        ):
            raise ValueError("expected_rgb must contain three integers in [0, 255]")
        rgb = self._rgb(image)
        region, selected = self._selection(rgb.shape, roi, mask)
        actual = rgb[region]
        expected = np.broadcast_to(np.array(expected_rgb, dtype=np.uint8), actual.shape)
        return self._compare(actual, expected, selected, delta_e_tolerance)
