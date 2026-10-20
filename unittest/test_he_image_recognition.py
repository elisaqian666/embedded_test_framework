import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("skimage")
from embedded_test_framework.helpers.he_image_recognition import ImageRecognitionHelper  # noqa: E402
from PIL import Image, ImageCms  # noqa: E402


def test_local_color_defect_is_not_hidden_by_average(tmp_path):
    helper = ImageRecognitionHelper()
    reference = np.zeros((10, 10, 3), dtype=np.uint8)
    actual = reference.copy()
    actual[3, 4] = 255
    result = helper.compare(actual, reference, delta_e_tolerance=1)
    assert result.pixel_count == 100
    assert result.matched_fraction == 0.99
    assert result.max_delta_e == pytest.approx(100, abs=0.001)
    assert result.mean_delta_e == pytest.approx(1, abs=0.001)
    assert result.p95_delta_e == 0
    assert result.mismatch_mask.getbbox() == (4, 3, 5, 4)
    result.mismatch_mask.save(tmp_path / "failure.png")
    with Image.open(tmp_path / "failure.png") as saved:
        assert saved.getpixel((4, 3)) == 255
    result.assert_match(0.99)
    with pytest.raises(AssertionError, match="Color match"):
        result.assert_match()
    assert np.count_nonzero(reference) == 0


def test_color_patches_roi_and_overlay_mask():
    helper = ImageRecognitionHelper()
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    image[:, :3] = [255, 0, 0]
    image[:, 3:] = [0, 0, 255]
    result = helper.match_color(image, (255, 0, 0), delta_e_tolerance=0)
    assert result.matched_fraction == 0.5
    helper.match_color(image, (255, 0, 0), delta_e_tolerance=0, roi=(0, 0, 3, 4)).assert_match()
    mask = np.ones((4, 6), dtype=bool)
    mask[:, 3:] = False
    result = helper.match_color(image, (255, 0, 0), delta_e_tolerance=0, mask=mask, roi=(1, 1, 5, 4))
    result.assert_match()
    assert result.pixel_count == 6
    assert result.mismatch_mask.size == (4, 3)
    assert result.mismatch_mask.getbbox() is None


def test_pixel_positions_matter_even_with_identical_histograms():
    image = np.array([[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8)
    result = ImageRecognitionHelper().compare(image, image[:, ::-1], delta_e_tolerance=2)
    assert result.matched_fraction == 0


def test_file_icc_and_pil_inputs_are_equivalent_and_not_modified(tmp_path):
    image = Image.new("RGB", (2, 2), (120, 80, 40))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path = tmp_path / "tagged.png"
    image.save(path, icc_profile=profile)
    helper = ImageRecognitionHelper()
    helper.compare(path, image, delta_e_tolerance=0).assert_match()
    helper.compare(image.convert("RGBA"), image, delta_e_tolerance=0).assert_match()
    helper.compare(image.convert("P", palette=Image.Palette.ADAPTIVE), image, delta_e_tolerance=0).assert_match()
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (120, 80, 40)
    path.unlink()  # No open file handle remains on Windows.


@pytest.mark.parametrize("roi", [(-1, 0, 1, 1), (0, 0, 3, 1), (1, 0, 1, 1), (0, 0, 1.0, 1), (0, 1)])
def test_invalid_roi_is_rejected(roi):
    with pytest.raises(ValueError, match="ROI"):
        ImageRecognitionHelper().match_color(Image.new("RGB", (2, 2)), (0, 0, 0), delta_e_tolerance=1, roi=roi)


@pytest.mark.parametrize("mask", [np.zeros((2, 2), dtype=bool), np.ones((1, 1), dtype=bool), np.ones((2, 2), dtype=np.uint8)])
def test_invalid_or_empty_mask_is_rejected(mask):
    with pytest.raises(ValueError):
        ImageRecognitionHelper().match_color(Image.new("RGB", (2, 2)), (0, 0, 0), delta_e_tolerance=1, mask=mask)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "2"])
def test_invalid_tolerance_is_rejected(value):
    with pytest.raises(ValueError, match="delta_e_tolerance"):
        ImageRecognitionHelper().match_color(Image.new("RGB", (2, 2)), (0, 0, 0), delta_e_tolerance=value)


@pytest.mark.parametrize(
    "image",
    [
        Image.new("RGBA", (2, 2), (255, 0, 0, 0)),
        Image.new("I;16", (2, 2)),
        np.zeros((2, 2, 3), dtype=float),
        np.zeros((2, 2), dtype=np.uint8),
        np.zeros((0, 2, 3), dtype=np.uint8),
    ],
)
def test_ambiguous_image_formats_are_rejected(image):
    with pytest.raises(ValueError):
        ImageRecognitionHelper().match_color(image, (0, 0, 0), delta_e_tolerance=1)


@pytest.mark.parametrize("color", [(256, 0, 0), (-1, 0, 0), (True, 0, 0), (0, 0), "red"])
def test_invalid_color_is_rejected(color):
    with pytest.raises(ValueError, match="expected_rgb"):
        ImageRecognitionHelper().match_color(Image.new("RGB", (2, 2)), color, delta_e_tolerance=1)


def test_dimensions_missing_file_and_corrupt_profile_fail(tmp_path):
    helper = ImageRecognitionHelper()
    image = Image.new("RGB", (2, 2))
    with pytest.raises(ValueError, match="identical dimensions"):
        helper.compare(image, Image.new("RGB", (3, 3)), delta_e_tolerance=1)
    with pytest.raises(FileNotFoundError):
        helper.compare(tmp_path / "missing.png", image, delta_e_tolerance=1)
    image.info["icc_profile"] = b"invalid profile"
    with pytest.raises(OSError):
        helper.match_color(image, (0, 0, 0), delta_e_tolerance=1)


def test_tolerance_is_inclusive_and_fraction_is_validated():
    helper = ImageRecognitionHelper()
    image = Image.new("RGB", (1, 1), (1, 1, 1))
    delta = helper.match_color(image, (0, 0, 0), delta_e_tolerance=0).max_delta_e
    result = helper.match_color(image, (0, 0, 0), delta_e_tolerance=delta)
    result.assert_match()
    for invalid in (-1, 1.01, float("nan"), True):
        with pytest.raises(ValueError):
            result.assert_match(invalid)


def test_find_camera_color_regions_and_filter_noise():
    image = np.full((40, 60, 3), 128, dtype=np.uint8)
    image[2:12, 3:15] = [180, 20, 20]
    image[15:35, 20:35] = [20, 160, 30]
    image[5:15, 45:55] = [20, 30, 200]
    image[30, 1] = [255, 0, 0]
    helper = ImageRecognitionHelper()
    for color, bbox, area in [("red", (3, 2, 15, 12), 120), ("green", (20, 15, 35, 35), 300), ("blue", (45, 5, 55, 15), 100)]:
        patches = helper.find_color_regions(image, color)
        assert len(patches) == 1
        assert (patches[0].color, patches[0].bbox, patches[0].pixel_count) == (color, bbox, area)
    patches = helper.find_color_regions(image, "red", min_area=1)
    assert [patch.pixel_count for patch in patches] == [120, 1]


def test_regions_use_full_image_coordinates_and_mask_clips_patches():
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[5:15, 10:25] = [0, 255, 0]
    mask = np.ones((20, 30), dtype=bool)
    mask[:, 20:] = False
    patches = ImageRecognitionHelper().find_color_regions(image, "green", roi=(12, 7, 27, 17), mask=mask)
    assert patches[0].bbox == (12, 7, 20, 15)
    assert patches[0].pixel_count == 64


def test_red_wraparound_dark_and_achromatic_pixels():
    image = np.array([[[255, 0, 20], [255, 20, 0], [255, 255, 255], [0, 0, 0], [30, 0, 0]]], dtype=np.uint8)
    helper = ImageRecognitionHelper()
    patches = helper.find_color_regions(image, "red", min_area=1)
    assert len(patches) == 1
    assert patches[0].pixel_count == 2
    assert helper.find_color_regions(image, "blue", min_area=1) == []
    patches = helper.find_color_regions(image, "red", min_area=1, min_saturation=0, min_value=0)
    assert [patch.pixel_count for patch in patches] == [2, 1]
    assert helper.find_color_regions(image, "red", min_area=1, hue_range=(0, 10))[0].pixel_count == 1


def test_diagonal_patches_are_separate():
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[0, 0] = image[1, 1] = [0, 0, 255]
    assert len(ImageRecognitionHelper().find_color_regions(image, "blue", min_area=1)) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"color": "yellow"},
        {"min_area": 0},
        {"min_area": True},
        {"min_saturation": float("nan")},
        {"min_value": 1.1},
        {"hue_range": (0, 361)},
        {"hue_range": (0,)},
        {"hue_range": "red"},
    ],
)
def test_invalid_region_detection_options(kwargs):
    options = {"color": "red", **kwargs}
    with pytest.raises(ValueError):
        ImageRecognitionHelper().find_color_regions(Image.new("RGB", (2, 2)), **options)
