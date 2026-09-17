"""
- Purpose:      as helper to control/handle the image
- Author:       KUNDW.
- Created:      06/07/2017.
- Copyright:    (c) Barco 2017.
- License:      All Rights Reserved.
"""

import difflib
import io
import logging
import math
import operator
import os
from collections import Counter
from functools import reduce

import cv2
import numpy
from barco_pytesseract import pytesseract
from PIL import Image, ImageChops, ImageFilter

from TEnTo.configurator.config_labels import LOGGERS


class ColorsRGB:
    black = (0, 0, 0)
    white = (255, 255, 255)
    red = (255, 0, 0)
    green = (0, 255, 0)
    blue = (0, 0, 255)


class ImageHelper(object):
    """ImageHelper Class"""

    logger = logging.getLogger(LOGGERS.HELPER)
    black_tr_color = (0, 0, 0, 0)
    """tuple representing the black color"""

    def open_image(self, image_path):
        """create an new image of the required size and color mode.

        :param image_path: The path of the image on which the action needs to be performed
        :return: PIL image.
        :rtype: PIL.Image.Image
        """
        self.logger.debug("open_image: {})".format(image_path))
        if not os.path.isfile(image_path):
            raise ValueError(f"file {image_path} not found.")
        return Image.open(image_path)

    def open_image_from_memory(self, img_bytes):
        """create an new image from bytes image in memory

        :return: PIL image.
        """
        self.logger.debug("open_image_from_memory: {})".format(img_bytes))
        return Image.open(io.BytesIO(img_bytes))

    def close_image(self, img):
        """close image.

        :param img: file to be closed
        """
        self.logger.debug("close_image: {})".format(img))
        img.close()

    def save_image(self, img, path):
        """save image @ given path.

        :param img: the image content to be saved
        :param path: The path where to save the image
        """
        if path.endswith(".jpg") and img.mode == "RGBA":
            img = img.convert("RGB")
        self.logger.debug("save_image: {im} to {pth})".format(im=img, pth=path))
        img.save(path)

    def save_jpg_copy(self, path):
        image = self.open_image(path)
        self.save_image(image, path[:-4] + ".jpg")
        self.close_image(image)
        del image

    def create_image(self, mode, w, h, color=None):
        """create an new image of the required size and color mode.

        :param mode: string 'RGB','L','1','CMYK',....
                    1 (1-bit pixels, black and white, stored with one pixel per byte)
                    L (8-bit pixels, black and white)
                    P (8-bit pixels, mapped to any other mode using a color palette)
                    RGB (3x8-bit pixels, true color)
                    RGBA (4x8-bit pixels, true color with transparency mask)
                    CMYK (4x8-bit pixels, color separation)
                    YCbCr (3x8-bit pixels, color video format)
                    Note that this refers to the JPEG, and not the ITU-R BT.2020, standard
                    LAB (3x8-bit pixels, the L*a*b color space)
                    HSV (3x8-bit pixels, Hue, Saturation, Value color space)
                    I (32-bit signed integer pixels)
                    F (32-bit floating point pixels)
        :param w: width of image
        :param h: height of image
        :param color: the default color (black) is applied if none
        :return: new empty image created.
        """
        self.logger.debug("create Image: {m}, {w},{h}, color={c}".format(m=mode, w=w, h=h, c=color if color else "default"))
        return Image.new(mode, (w, h), color)

    def split_image_horizontal(self, image_path):
        """Splits the image horizontally into two halves from the center.

        :param image_path: The path of the image on which the action needs to be performed
        :return: return 2 images left,right
        """
        src_image = self.open_image(image_path)
        img_left = self.extract_from_image(src_image, 0, 0, src_image.width / 2, src_image.height)
        img_right = self.extract_from_image(src_image, src_image.width / 2, 0, src_image.width, src_image.height)
        self.close_image(src_image)
        self.logger.debug("Image Horizontal split successful")
        return img_left, img_right

    def extract_from_image(self, src_image, left, up, right, low):
        """extract a sub-image from source image.

        :param src_image: source Image
        :param left: left-coordinate of sub-image to extract
        :param up: up-coordinate of sub-image to extract
        :param right: right coordinate of sub-image to extract
        :param low: low coordinate of sub-image to extract
        :return: images
        """
        self.logger.debug("Image cropping (%d,%d,%d,%d)" % (left, up, right, low))
        return src_image.crop((left, up, right, low))

    def insert_in_image(self, src_image, region, left, up, right, low):
        """insert a sub-image into source image.

        :param src_image: source Image
        :param region: region to paste
        :param left: left-coordinate of sub-image to extract
        :param up: up-coordinate of sub-image to extract
        :param right: right coordinate of sub-image to extract
        :param low: low coordinate of sub-image to extract
        """
        self.logger.debug("Image insert @ location (%d,%d,%d,%d)" % (left, up, right, low))
        src_image.paste(region, (left, up, right, low))

    def resize_image(self, src_image, w, h):
        """resize source image (downscale/upscale).

        :param src_image: source Image
        :param w: new width of image
        :param h: new height of image
        :return: resized image
        """
        self.logger.debug("resize_image: {im}, ({w},{h})".format(im=src_image, w=w, h=h))
        return src_image.resize((w, h), Image.Resampling.LANCZOS)

    def thumbnail(self, src_img, w, h):
        """return thumbnail from source @ dimension."""
        self.logger.debug("thumbnail: {im}, ({w},{h})".format(im=src_img, w=w, h=h))
        thumb = src_img.copy()
        thumb.thumbnail((w, h))
        return thumb

    def get_numpy_array(self, src_image):
        """return numpy array from the source image.

        :param src_image: source Image
        :type src_image: PIL.Image.Image
        :return: numpy array
        """
        self.logger.debug("get_numpy_array: {}".format(src_image))
        return numpy.asarray(src_image)

    def get_image_from_array(self, src_array):
        """return image from array source.

        :param src_array: byte array
        :return: pillow Image
        :rtype: PIL.Image.Image
        """
        self.logger.debug("get_Image_from_array: {}".format(src_array))
        return Image.fromarray(src_array)

    def get_black_box_area(self, src_image):
        """return detected blackbox area in image.

        :param src_image: image source to check
        :type src_image: PIL.Image.Image
        :return: tuple(left,top,right,bottom)
        """
        self.logger.debug("get_black_box_area Image {}".format(src_image))
        return src_image.getbbox()

    def get_black_box_ish_area(self, src_image, th=0.2):
        """return detected blackbox-ish area in image: end colors are not same as color on pc
        because color map is changed in process to send data to unit and display due to re-encoding.

        :param src_image: image source to check
        :type src_image: PIL.Image.Image
        :param th: threshold for determination of black-ish
        :return: tuple(left,top,right,bottom)
        """
        self.logger.debug("get_blackish_box_area Image {}".format(src_image))
        pixels = self.get_numpy_array(src_image)

        def binary_check_bbx(array_pixels, start, size, hor=True, reverse=False, threshold=th):
            def get_pixels_area(arr_pixels, pix_lines, start_index, end_index):
                last_in_array = min(end_index, len(arr_pixels[:]) - 1 if pix_lines else len(arr_pixels[0][:]) - 1)
                if start_index < last_in_array:
                    return arr_pixels[start_index:last_in_array, :] if pix_lines else arr_pixels[:, start_index:last_in_array]
                else:
                    return arr_pixels[last_in_array, :] if pix_lines else arr_pixels[:, last_in_array]

            if size <= 1:  # @ least 1 vector in matrix to check
                return start
            a_size = round(size / 2)
            end_array = len(array_pixels[:]) - 1 if hor else len(array_pixels[0][:]) - 1
            left_start = start if not reverse else min(start + a_size, end_array)
            right_start = min(start + a_size, end_array) if not reverse else start
            bck = numpy.mean(get_pixels_area(array_pixels, hor, left_start, left_start + a_size))
            if bck >= threshold:
                return binary_check_bbx(array_pixels, left_start, a_size, hor, reverse, threshold)
            else:
                return binary_check_bbx(array_pixels, right_start, a_size, hor, reverse, threshold)

        bbx_t = binary_check_bbx(pixels, 0, src_image.height)
        bbx_b = binary_check_bbx(pixels, 0, src_image.height, reverse=True)
        bbx_l = binary_check_bbx(pixels, 0, src_image.width, hor=False)
        bbx_r = binary_check_bbx(pixels, 0, src_image.width, hor=False, reverse=True)
        self.logger.info(f"found: {(bbx_l, bbx_t, bbx_r, bbx_b)}")
        return bbx_l, bbx_t, bbx_r, bbx_b  # return tuple format same as bbx from PIL

    def remove_bbox(self, src_image, area=None):
        """remove Black bar from image by cropping.

        :param src_image: image
        :param area: tuple of bbx to remove
        :return: PIL Image cropped to (image-BlBar)
        """
        bbx = area if area else self.get_black_box_area(src_image)
        return self.extract_from_image(src_image, bbx[0], bbx[1], bbx[2], bbx[3])

    def grey_scale(self, src_image):
        """convert source image to grey scale.

        :param src_image: source Image
        :return: converted image
        """
        self.logger.info("Image converted to 'L' mode (grey scale)")
        return src_image.convert(mode="L")

    def sharpen_image(self, src_image):
        """sharpen filter on source image.

        :param src_image: source Image
        :return: sharpened image
        """
        self.logger.debug("sharpen Image {}".format(src_image))
        return src_image.filter(ImageFilter.SHARPEN)

    def smooth_image(self, src_image):
        """smooth filter on source image.

        :param src_image: source Image
        :return: smoothed image
        """
        self.logger.debug("smooth Image {}".format(src_image))
        return src_image.filter(ImageFilter.SMOOTH_MORE)

    def equal(self, im1, im2):
        """compare exactly 2 images on content minus black boxes around.

        :param im1: source Image to compare
        :param im2: source Image to compare
        :return: True if images are equal
        """
        self.logger.debug("check image equal {im1},{im2}".format(im1=im1, im2=im2))
        return self.image_difference(im1, im2).getbbox() is None

    @staticmethod
    def convert_image_mode(im_ref, im):
        """convert im2 to im1 mode as a gen3ric approach to convert 2 image <> mode

        :param im_ref: image is reference
        :param im: image to be converted
        :return: im converted to mode of im_ref
        """
        # normally we mostly use RGB, but helper must be generic, if not same format then just convert to im1 format
        # conversion are very complex and would involve much work to be good but just do basics since we mostly use RGB format
        if im_ref.mode != im.mode:
            im = im.convert(im_ref.mode)
        return im

    def image_difference(self, im1, im2):
        """return diff content between 2 images

        :param im1: source Image to compare
        :param im2: source Image to compare
        :return: PIL image difference of both in RGB mode
        :rtype: PIL.Image.Image
        """
        self.logger.debug("image diff: {im1},{im2}".format(im1=im1, im2=im2))
        im2 = self.convert_image_mode(im1, im2)
        return ImageChops.difference(im1, im2)

    def rmsdiff_histogram(self, im1, im2):
        """Calculate the root-mean-square difference between two images on complete histogram

        :param im1: 1rst image to use for diff
        :param im2: 2nd image  to use for diff
        """
        self.logger.debug("rmsdiff_histogram {im1}, {im2}".format(im1=im1, im2=im2))
        histogram = self.image_difference(im1, im2).histogram()
        # calculate rms
        return math.sqrt(
            reduce(operator.add, map(lambda hist, i: hist * ((i % 256) ** 2), histogram, range(len(histogram))))
            / (float(im1.size[0]) * im1.size[1])
        )

    def rms_rgb_band(self, im1, im2):
        """Calculate the root-mean-square difference between two images for 3 band.

        :param im1: First RGB image to be used in comparison
        :param im2: Second RGB image to be used in comparison
        :return: root-mean-square difference between two images for each color channel
        """
        im1 = im1.convert("RGB")
        im2 = im2.convert("RGB")
        r1, g1, b1 = im1.split()
        r2, g2, b2 = im2.split()
        # calculate rms
        return self.rmsdiff_histogram(r1, r2), self.rmsdiff_histogram(g1, g2), self.rmsdiff_histogram(b1, b2)

    def calculate_ssim(self, im1, im2, size_sliding_window=11):
        """SSIM structural similarity index measure quality assessment index is based on the computation of three terms,
            - luminance term,
            - the contrast term
            - structural term.

        The overall index is a multiplicative combination of the three terms.
        SSIM(x,y)=[l(x,y)]^α.[c(x,y)]^β.[s(x,y)]^γ
        where
        - l(x,y)=(2μxμy+C1)/(μx^2+μy^2+C1)  luminance term
        - c(x,y)=(2σxσy+C2)/σx^2+σy^2+C2    contrast term
        - s(x,y)=(σxy+C3)/(σxσy+C3)         structural term

        By default,
            C1 = (0.01*L).^2, where L is the specified DynamicRange value.
            C2 = (0.03*L).^2, where L is the specified DynamicRange value.
            C3 = C2/2

        DynamicRange value = sizeof(data), default sizeof(UINT8)=255
        where μx, μy, σx,σy, and σxy are the local means, standard deviations, and cross-covariance for images x, y. If α = β = γ = 1
        (the default for Exponents), and C3 = C2/2 (default selection of C3) the index simplifies to:
        SSIM(x,y)=((2μxμy+C1)*(2σxy+C2))/((μx^2+μy^2+C1)(σx^2+σy^2+C2))

        :param im1: source image to compare to
        :param im2: image to compare to source
        :param size_sliding_window: size of sliding window to use, 0 to disable and calculate mean over
                                    image default 11 as per reference (http://www.cns.nyu.edu/~lcv/ssim/)
        :return: ssim score is 1.0 when images are exactly same, else goes down towards 0 depending on similarity the closer to 1,
                 the more similar are images
        """
        dynamic_data_range = 255
        c1 = (0.01 * dynamic_data_range) * (0.01 * dynamic_data_range)
        c2 = (0.03 * dynamic_data_range) * (0.03 * dynamic_data_range)
        # grey image to get 1 dimension for convolution not RGB
        im1 = self.grey_scale(src_image=im1)
        im2 = self.grey_scale(src_image=im2)
        mat_im1 = self.get_numpy_array(im1)
        mat_im2 = self.get_numpy_array(im2)
        # build a filter sliding window normalized
        if size_sliding_window:
            sliding_win_size = int(max(1, round(min(im1.size) / 256)))
            mx_one = numpy.ones((sliding_win_size, sliding_win_size))
            mx_one_normalized = mx_one / sum(mx_one)
            # make a convolution so apply filter sliding over the src matrix, it will give u a matrix of src.size-(filter_size-1)
            mat_cv_im1 = self._convolution_2d(mat_im1, mx_one_normalized)
            mat_cv_im2 = self._convolution_2d(mat_im2, mx_one_normalized)
            # down-sample matrix to filter_size
            mat_ds_im1 = self._downsample_2d(mat_cv_im1, sliding_win_size)
            mat_ds_im2 = self._downsample_2d(mat_cv_im2, sliding_win_size)
            # convolution using sliding window
            size_sliding_window = int(size_sliding_window)
            mx_window = numpy.ones((size_sliding_window, size_sliding_window))
            mx_window_normalized = mx_window / sum(sum(mx_window))
            ux = self._convolution_2d(mat_ds_im1, mx_window_normalized)
            uy = self._convolution_2d(mat_ds_im2, mx_window_normalized)
            ux_sq = ux * ux
            uy_sq = uy * uy
            uxy = ux * uy
            sigma1_sq = self._convolution_2d(mat_ds_im1 * mat_ds_im1, mx_window_normalized) - ux_sq
            sigma2_sq = self._convolution_2d(mat_ds_im2 * mat_ds_im2, mx_window_normalized) - uy_sq
            sigma12 = self._convolution_2d(mat_ds_im1 * mat_ds_im2, mx_window_normalized) - uxy
        else:
            mx_one = numpy.ones(mat_im1.shape)
            mx_one_normalized = mx_one / sum(mx_one)
            mat_ds_im1 = mat_im1 / sum(mx_one_normalized)
            mat_ds_im2 = mat_im2 / sum(mx_one_normalized)
            # calculate ssim
            ux = numpy.mean(mat_ds_im1)
            uy = numpy.mean(mat_ds_im2)
            ux_sq = ux * ux
            uy_sq = uy * uy
            uxy = ux * uy
            # we consider that we have a gaussian behavior
            sigma1_sq = (mat_ds_im1 * mat_ds_im1).mean() - ux_sq
            sigma2_sq = (mat_ds_im2 * mat_ds_im2).mean() - uy_sq
            sigma12 = (mat_ds_im1 * mat_ds_im2).mean() - mat_ds_im1.mean() * mat_ds_im2.mean()
        # ssim calculation: matrix or number
        ssim = ((2 * uxy + c1) * (2 * sigma12 + c2)) / ((ux_sq + uy_sq + c1) * (sigma1_sq + sigma2_sq + c2))
        if size_sliding_window:
            ssim = numpy.mean(ssim)
        return ssim

    @staticmethod
    def _convolution_2d(mx, f):
        """convolution of filter f onto matrix mx

        :param mx: matrix source
        :param f: filter sliding window to convolve over matrix
        :return: convolution 2d of f into mx
        """
        s = f.shape + tuple(numpy.subtract(mx.shape, f.shape) + 1)
        strd = numpy.lib.stride_tricks.as_strided
        subm = strd(mx, shape=s, strides=mx.strides * 2)
        return numpy.einsum("ij,ijkl->kl", f, subm)

    @staticmethod
    def _downsample_2d(mx, f_size):
        """down sample matrix by size of filter size

        :param mx: matrix to downsample
        :param f_size: size of filter
        :return: down-sampled 2D matrix
        """
        return mx[0::f_size, 0::f_size]

    def split_screenshot(self, screenshot_name, number=2):
        """function to split the image vertically in the defined number of times.

        :param screenshot_name: name of the screenshot which needs to be split
        :param number: the number of times the image needs to be split.
        :return: split image list
        """
        if not os.path.exists(screenshot_name):
            raise ValueError(f"this image {screenshot_name} is not found")
        img = self.open_image(screenshot_name)
        img_list = numpy.split(self.get_numpy_array(src_image=img), number, 1)
        self.close_image(img)
        image_list = []
        for i in range(number):
            image_name = f"{screenshot_name[:-4]}_{str(i + 1)}.png"
            img_splt = self.get_image_from_array(img_list[i])
            self.save_image(img=img_splt, path=image_name)
            del img_splt
            image_list.append(image_name)
        return image_list

    def check_images_almost_equal(self, im1, im2, threshold=(10.0, 0.9)):
        """check if 2 images of same resolution are every similar

        :param im1: image 1
        :param im2: image 2
        :param threshold: tuple(mse,ssim) thresholds can be set by caller
        :return: True if very similar using thresholds given else False
        """
        if im1.size != im2.size:
            raise ValueError(f"u can only compare similarity of same images size: {im1.size} {im2.size}")
        res_mse = self.rms_rgb_band(im1, im2)
        res_ssim = self.calculate_ssim(im1, im2)
        th_mse = threshold[0]
        if not isinstance(th_mse, tuple):
            th_mse = [th_mse] * 3
        th_ssim = threshold[1]
        final_result = (res_mse[0] <= th_mse[0] and res_mse[1] <= th_mse[1] and res_mse[2] <= th_mse[2]) or res_ssim >= th_ssim
        if not final_result:
            diff_img = self.image_difference(im1, im2)
            self.save_image(diff_img, "debug_diff_{}.jpg".format(int(res_ssim * 1000)))
        self.logger.info(
            "results: [{w},{h}]  thr={t} - mse={rms}, ssim={ssim} => {r}".format(
                w=im1.width, h=im1.height, t=threshold, rms=res_mse, r=final_result, ssim=res_ssim
            )
        )
        return final_result

    def capture_area(self, input_image_name, element_name, coord, resolution=None):
        """capture an element in image and save it to in reference resolution.

        :param input_image_name: screen shot to extract from (pc or base_unit or ...)
        :param element_name: name of the element captured to save
        :param coord: coordinates (x_t, y_t, x_b, y_b) top/bottom of the area to capture
        :param resolution: None if coordinate as per image resolution else resolution where capture coordinates apply
        :return: name of the element capture file
        """
        if (
            not coord
            or not element_name
            or resolution
            and (
                coord[0] not in range(resolution[0])
                or coord[2] not in range(resolution[0] + 1)
                or coord[1] not in range(resolution[1])
                or coord[3] not in range(resolution[1] + 1)
            )
        ):
            raise ValueError(f"input incorrect: {element_name}, {coord}, {resolution}")
        img_screen = self.open_image(input_image_name)
        img_screen_resized = img_screen
        if resolution and (img_screen_resized.width != resolution[0] or img_screen_resized.height != resolution[1]):
            img_screen_resized = self.resize_image(img_screen_resized, resolution[0], resolution[1])
        img_screen_resized = self.extract_from_image(img_screen_resized, coord[0], coord[1], coord[2], coord[3])
        element_name += ".png"
        self.save_image(img_screen_resized, element_name)
        self.close_image(img_screen)
        self.logger.info("captured: {name}=({w},{h})".format(name=element_name, w=img_screen_resized.width, h=img_screen_resized.height))
        return element_name

    def compare_areas(self, input_image_name, top_coord, ref_image_name, ref_res=None, threshold=(20.0, 0.8)):
        """compare an image (in reference resolution) with screen area starting @ coordinate and return how close it is.

        :param input_image_name: path and name of input image to analise
        :param top_coord: x,y coordinate of screen part in screen shot image resolution
        :param ref_image_name: None or path and name of reference image to compare to
        :param ref_res: resolution where the reference coordinates applies or None if same as image input
        :param threshold: tuple threshold of comparison for equality using MSE/SSIM
        :return: True if image close to reference according threshold
        """
        im_base = self.open_image(ref_image_name)
        img_screen = self.open_image(input_image_name)
        img_screen_resized = img_screen
        if ref_res and (img_screen.width != ref_res[0] or img_screen.height != ref_res[1]):
            img_screen_resized = self.resize_image(img_screen_resized, ref_res[0], ref_res[1])
        img_screen_resized = self.extract_from_image(
            img_screen_resized, top_coord[0], top_coord[1], top_coord[0] + im_base.width, top_coord[1] + im_base.height
        )
        final_result = self.check_images_almost_equal(im_base, img_screen_resized, threshold)
        if not final_result:  # save png of area if failed for investigation afterwards
            self.save_image(img_screen_resized, "debug_{0}.png".format((os.path.basename(input_image_name)[:-4])))
        self.close_image(im_base)
        self.close_image(img_screen)
        return final_result

    def compare_captured_image_with_list_images(self, pc_img, list_ref_img, list_threshold=[(20, 0.9)], crop_window=None):
        """compare given image with list images given and return results.

        :param pc_img: PIL input image to compare with PIL images from list
        :param list_ref_img: list of PIL image to compare to input image
        :param list_threshold: list of threshold: tuple mse/ssim=(th_mse, th_ssim)|((tr,tg,tb),th_ssim))
                            where the_mse is 1 number or a tuple per (R,G,B)
        :param crop_window: (l,t,b,r) window to crop to for comparison
        :return: list of result of comparison for each image in reference list
        """
        len_thresholds = len(list_threshold)
        if len_thresholds > 1 and len_thresholds != len(list_ref_img):
            raise ValueError("mismatch images/thresholds : give 1 threshold for all or each a threshold.")
        im_pc_cropped = pc_img
        if crop_window:
            im_pc_cropped = self.extract_from_image(pc_img, crop_window[0], crop_window[1], crop_window[2], crop_window[3])
        results_compare = []
        for img_ref in list_ref_img:
            index = list_ref_img.index(img_ref)
            if len(list_threshold) > 1:
                cur_threshold = list_threshold[index]
            else:
                cur_threshold = list_threshold[0]
            if img_ref.size != pc_img.size:
                img_ref_cropped = self.resize_image(img_ref, pc_img.width, pc_img.height)
            else:
                img_ref_cropped = img_ref
            if crop_window:
                img_ref_cropped = self.extract_from_image(img_ref_cropped, crop_window[0], crop_window[1], crop_window[2], crop_window[3])
            results_compare.append(self.check_images_almost_equal(img_ref_cropped, im_pc_cropped, cur_threshold))
        return results_compare

    def open_check_image_similarity(self, im1_name, im2_name, threshold=(10, 0.9)):
        """open images and check similarity

        :param im1_name: image name
        :param im2_name: image name
        :param threshold: tuple(mse,ssim) threshold to validate similarity
        :return: False if both threshold not met else True
        """
        im1 = self.open_image(im1_name)
        im2 = self.open_image(im2_name)
        final_result = self.check_images_almost_equal(im1, im2, threshold)
        self.close_image(im1)
        self.close_image(im2)
        return final_result

    def trim_image_width_to_smallest_width(self, img1, img2):
        """Compares 2 images and trims the widest equally on both left and right side to match the width of the smallest image.

        :param img1: PIL image.
        :param img2: PIL image.
        :return: Both PIL images in the same order that they were passed.
        """
        width_pixel_difference = abs(img1.width - img2.width)
        if width_pixel_difference == 0:
            return img1, img2
        elif img1.width > img2.width:
            image_that_needs_cutting = img1
            image_that_stays_the_same = img2
        else:
            image_that_needs_cutting = img2
            image_that_stays_the_same = img1

        image_that_is_cut = self.extract_from_image(
            image_that_needs_cutting,
            math.floor(width_pixel_difference / 2),
            0,
            image_that_needs_cutting.width - math.ceil(width_pixel_difference / 2),
            image_that_needs_cutting.height,
        )
        if img1.width > img2.width:
            return image_that_is_cut, image_that_stays_the_same
        else:
            return image_that_stays_the_same, image_that_is_cut

    def resize_image_maintain_aspect_ratio(self, image, target_height):
        """Resizes a given image to the requested height, while maintaining the aspect ratio.

        :param image: PIL image.
        :param target_height: Requested height in pixel count.
        :return: Resized PIL image.
        """
        height_ratio = target_height / image.height
        target_width = round(image.width * height_ratio)
        return self.resize_image(image, int(target_width), int(target_height))

    @staticmethod
    def is_pixel_blackish(pixel_to_check, r_g_b_blackish_threshold=2):
        """Checks if a pixels Red Green Blue value's are all below 2(default) out of 255.
        :param pixel_to_check: (R, G, B) tuple.
        :param r_g_b_blackish_threshold: the value the r, g and b value should be under, to be considered black enough.
        :return: Boolean indicating if pixel is blackish.
        :rtype: bool
        """
        return (
            (pixel_to_check[0] < r_g_b_blackish_threshold)
            & (pixel_to_check[1] < r_g_b_blackish_threshold)
            & (pixel_to_check[2] < r_g_b_blackish_threshold)
        )

    def is_row_pixel_mostly_black(self, row_to_check, mostly_black_threshold_ratio=0.98):
        """Checks if a row of pixels is mostly blackish using the is_pixel_blackish method in ImageHelper.
        :param row_to_check: an iterable list of RGB pixel value's.
        :param mostly_black_threshold_ratio: threshold ratio that must be reached to judge the iterable list of pixels mostly black.
        :return: Boolean indicating if a row of pixels is blackish.
        :rtype: bool
        """
        count = Counter(self.is_pixel_blackish(elem) for elem in row_to_check)
        black_percentage = count[True] / (count[True] + count[False])
        return black_percentage >= mostly_black_threshold_ratio

    def _sharpen_image_for_ocr_detection(self, image_path, invert_color=True):
        """sharpen/transform image to improve OCR detection results

        :param image_path: target image path
        :param invert_color: invert color of image if True
        :return: result as PIL image
        """
        image = cv2.imread(image_path)
        # Sharpen the provided image to increase the visibility of text
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        sharpen_kernel = numpy.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpen = cv2.filter2D(gray, -1, sharpen_kernel)
        thresh = sharpen
        if invert_color:
            thresh = cv2.threshold(sharpen, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        return self.get_image_from_array(thresh)

    def extract_text_from_image(self, image_path, save_img=False, language="eng", config="--psm 6", invert_color=True):
        """Sharpen the provided image to increase the visibility of text, and extract the text form the sharpen image
        https://pypi.org/project/pytesseract/

        :param image_path: the target image path
        :param save_img: save the sharpen image if True. default False
        :param language: language code string. Defaults to eng if not specified! Example for multiple languages: lang='eng+fra'
        :param config: any additional custom configuration flags not available via the pytesseract function. For example: config='--psm 6'
        :param invert_color: enable/disable color inversion before decoding
        :return: return the extracted text
        :rtype: str
        """
        img_thresh = self._sharpen_image_for_ocr_detection(image_path, invert_color)
        if save_img:
            sharpen_img_name = image_path.replace(".png", "_sharpen.png")
            self.logger.info("The sharpen image file saved {0}".format(self.save_image(img_thresh, sharpen_img_name)))
        text_from_image = pytesseract.image_to_string(img_thresh, lang=language, config=config)
        self.logger.info("Image (inverted={ic}) extracted text is {tx}".format(ic=invert_color, tx=text_from_image.split("\n")))
        return text_from_image

    def extract_and_verify_ocr_decoding(
        self, image_path, expected_text, language="eng", config="--psm 6", invert_color=True, text_threshold=0.92
    ):
        """extract and verify OCR decoding

        :param image_path: path to target image
        :param expected_text: string or list of expected string to be decoded
        :param language: language used during decoding
        :param config: config used during decoding
        :param invert_color: enable/disable color inversion
        :param text_threshold: ratio of string match
        :return: list of element from reference found during decoding with the threshold accuracy
        """
        if not (isinstance(expected_text, str) or isinstance(expected_text, list)):
            raise ValueError(f"incorrect format for expected text: {expected_text}")
        expected_text = expected_text if isinstance(expected_text, list) else [expected_text]
        text_inverted_image = (self.extract_text_from_image(image_path, language=language, config=config, invert_color=invert_color)).split(
            "\n"
        )
        self.logger.info("Expected: {e}\nExtracted txt inverted image:{it}".format(e=expected_text, it=text_inverted_image))
        found = {}
        for text in expected_text:
            result, decoded = self._find_ref_string_within_decoded_list(text, text_inverted_image, text_threshold)
            if result:
                found[text] = decoded
        self.logger.info(found)
        return found

    def _find_ref_string_within_decoded_list(self, reference_text, found_text, threshold=0.92):
        """find the closest string to reference string in decoded text list and return True if met and decoded text

        :param reference_text: list of reference string expected
        :param found_text: list of decoded text from OCR
        :param threshold: threshold of char <> accepted
        :return: True/False
        """
        result = False
        found = None
        if not reference_text or not found_text:
            raise ValueError(f"Expected {reference_text} or found {found_text} is not correct")
        for text in found_text:
            ds = difflib.SequenceMatcher(a=reference_text, b=text)
            ratio = ds.ratio()
            long_seq = list(ds.find_longest_match(0, len(reference_text), 0, len(text)))
            if long_seq[2]:
                self.logger.debug("SEQUENCE: {rt} <-> {txt}".format(rt=reference_text, txt=text[long_seq[1] :]))
                ds = difflib.SequenceMatcher(a=reference_text, b=text[long_seq[1] : len(reference_text)])
            ratio2 = ds.ratio()
            if reference_text in text or ratio >= threshold or ratio2 >= threshold:
                self.logger.info("Found score={d1} {d2}-> {rt}, {txt}".format(d1=ratio, d2=ratio2, rt=reference_text, txt=text))
                result = True
                found = text
                threshold = max(ratio, ratio2)
            if ratio > 0.8 or ratio2 > 0.8:
                self.logger.debug("debug: score={d1} {d2}-> {rt}, {txt}".format(d1=ratio, d2=ratio2, rt=reference_text, txt=text))
        return result, found

    @staticmethod
    def _max_rectangle_from_group(group_rows, group_cols, gr1, gr2):
        """return biggest rectangle out of the groups given

        :param group_rows: all rows groups found
        :param group_cols: all columns groups found
        :param gr1: keys for line/column of group 1
        :param gr2: keys for line/column of group 2
        :return: the biggest available rectangle inside the group given
        """
        r1, c1 = gr1
        r2, c2 = gr2
        return (min(group_cols[c1]), min(group_rows[r1]), max(group_cols[c2]), max(group_rows[r2]))

    @staticmethod
    def _min_rectangle_from_group(group_rows, group_cols, gr1, gr2):
        """return smallest rectangle out of the groups given

        :param group_rows: all rows groups found
        :param group_cols: all columns groups found
        :param gr1: keys for line/column of group 1
        :param gr2: keys for line/column of group 2
        :return: the biggest available rectangle inside the group given
        """
        r1, c1 = gr1
        r2, c2 = gr2
        return (max(group_cols[c1]), max(group_rows[r1]), min(group_cols[c2]), min(group_rows[r2]))

    @staticmethod
    def _check_segment_transparency(np_array_im, tr_color_mean, group, segment, vertical):
        """verify segment given is a transparent color segment

        :param np_array_im: numpy array of image
        :param tr_color_mean: transparent color mean value
        :param group: group of transparent lines, either line or column, vertical will allow distinction for operation
        :param segment: start/end index of segment
        :param vertical: flag for operating on line or column group
        :return: index line or column found
        """
        found = None
        s, e = segment
        max_mean = None
        min_index = 0
        max_index = len(np_array_im[0]) - 1 if vertical else len(np_array_im) - 1
        for index in group:
            mean = numpy.mean(np_array_im[s:e, index]) if vertical else numpy.mean(np_array_im[index, s:e])
            if mean == tr_color_mean or index == min_index or index == max_index:
                new_max = max(max_mean, mean) if max_mean is not None else mean
                if max_mean is None or max_mean < new_max:
                    found = index
                    max_mean = new_max
        return found

    @staticmethod
    def _analyse_image_colors(im):
        """analyze colors to find transparent colors list

        :param im: image to analyze
        :return:list of transparent color from image
        :rtype: list
        """
        l_tr_color = []
        colors = sorted(im.getcolors(im.size[0] * im.size[1]))
        for occurrence, color in reversed(colors):
            if color[3] != 0:
                continue
            if color not in l_tr_color:
                l_tr_color.append(color)
        return l_tr_color

    def _applies_transparent_colors(self, im, tr_color, force_color, revert=False):
        """force given color to be transparent colors and return a new image from it

        :param im: PIL Image format
        :param tr_color: list of transparent color tuple (r,g,b,a) extracted from image [result from _analyse_image_colors(im)]
        :param force_color: dictionary of color tuple to force to transparent color ((r,g,b) only for user, transparency not needed)
                {'list'[c1] or [c1,c2,...] or 'up':c1 or 'down':c1 or 'interval': [c1,c2] where cx is (r,g,b) tuple color
        :param: revert: revert appliance, default=False apply TC to matching filter else revert and apply TC to color not matching filter
        :return: new image with color applied as black transparent
        """

        def gte_color_tuple(c1, c2):
            return all(c1 >= c2 for c1, c2 in zip(c1, c2))

        def lte_color_tuple(c1, c2):
            return all(c1 <= c2 for c1, c2 in zip(c1, c2))

        new_imdata = []
        l_f_tr_color = None if not force_color or "list" not in force_color else force_color["list"]
        f_tr_color_thr_up = None if not force_color or "up" not in force_color else force_color["up"]
        f_tr_color_thr_down = None if not force_color or "down" not in force_color else force_color["down"]
        f_tr_color_range = None if not force_color or "interval" not in force_color else force_color["interval"]
        list_forced_color = []
        if l_f_tr_color:
            for fc in l_f_tr_color:
                expected_color = (fc[0], fc[1], fc[2], 255)
                list_forced_color.append(expected_color)
        self.logger.info("filtering to 1 transparent colors to 1")
        self.logger.info(f"im_tr_color={tr_color}-user_tr_color=({l_f_tr_color}-{list_forced_color})")
        self.logger.info(f"tr_threshold_up={f_tr_color_thr_up}-tr_threshold_down=({f_tr_color_thr_down})-tr_range={f_tr_color_range}")
        pixels_number = len(im.getdata())
        old_progress = 0
        for i, color in enumerate(im.getdata()):
            if (
                color in tr_color
                or (l_f_tr_color and color in list_forced_color)
                or (f_tr_color_thr_up and gte_color_tuple(color, f_tr_color_thr_up))
                or (f_tr_color_thr_down and lte_color_tuple(color, f_tr_color_thr_down))
                or (f_tr_color_range and gte_color_tuple(color, f_tr_color_range[0]) and lte_color_tuple(color, f_tr_color_range[1]))
            ):
                new_imdata.append(self.black_tr_color if not revert else color)
            else:
                new_imdata.append(color if not revert else self.black_tr_color)
            progress = int((i * 100) / pixels_number)
            if progress != old_progress:
                old_progress = progress
                self.logger.debug(f"progress convert to 1 transparent color: {progress}%")

        new_im = self.create_image(im.mode, im.width, im.height)
        new_im.putdata(new_imdata)
        return new_im

    def _save_debug_scanning_results(self, name, im_src, score_rows, score_cols):
        """save debug scan image if needed for algorithm debugging behavior

        :param name: name of the current file being checked
        :param im_src: image src
        :param score_rows: list of groups of rows candidates
        :param score_cols: list of groups of cols candidates
        """
        if name:
            im = im_src.copy()
            s_x = 0
            s_y = 0
            e_y = im.height - 1
            e_x = im.width - 1
            im_row_red = self.create_image("RGBA", e_x + 1, 1, (255, 0, 0, 255))
            im_col_red = self.create_image("RGBA", 1, e_y + 1, (255, 0, 0, 255))
            for row_group in score_rows:
                for row in score_rows[row_group]:
                    self.insert_in_image(im, im_row_red, s_x, row, e_x + 1, row + 1)
            for col_group in score_cols:
                for col in score_cols[col_group]:
                    self.insert_in_image(im, im_col_red, col, s_y, col + 1, e_y + 1)
            self.save_image(im, name)
            self.close_image(im)

    def _remove_group_under_accuracy_size(self, score_rows, score_cols, accuracy):
        """this was split from _scan to decrease complexity in sonarqube, sonarqube being not smart enough, aligning on weakest link
            This remove group of size < accuracy exclude start/end group (image border must stay in).
            This is meant to get rid of the 1 or few  lines split between items ... like between characters in strings.
            It was added after bazaar demo and helps selecting a granularity to the detection outcome.

        :param score_rows: list of groups of rows candidates
        :param score_cols: list of groups of column candidates
        :param accuracy: (l,c), accuracy per line, column to check versus
        :return: score_rows, score_cols cleaned up from small groups
        """
        list_row_group = list(score_rows.keys())
        for row_group in list_row_group[1:-1]:
            if len(score_rows[row_group]) < accuracy[1]:
                self.logger.debug(f"row pop group: {row_group} {score_rows.pop(row_group)}")
        list_col_group = list(score_cols.keys())
        for col_group in list_col_group[1:-1]:
            if len(score_cols[col_group]) < accuracy[0]:
                self.logger.debug(f"column pop group: {col_group} {score_cols.pop(col_group)}")
        return score_rows, score_cols

    def _scan_image_using_color_reference(self, im_src, name, accuracy, color_th):
        """scan image using a transparent color reference to split image in areas

        :param im_src: image source
        :param name: name of image being scanned to use for saving scanning debug if needed
        :param accuracy: tuple of min size of group of transparent to use, skip if less
        :param color_th: mean value of TC color (can be tuple row, column)
        :return: dict of groups  of adjacent row/column found over the image
        """
        npa_im = numpy.asarray(im_src)
        if not isinstance(color_th, list):
            color_th = [color_th] * 2
        row_group = None
        s_x = 0
        s_y = 0
        e_y = im_src.height - 1
        e_x = im_src.width - 1
        score_rows = {s_y: {s_y: 0}}
        score_cols = {s_x: {s_x: 0}}
        for row in range(e_y):
            value = numpy.mean(npa_im[row, s_x:e_x])
            if color_th[0] <= value <= color_th[1]:
                if row_group is None or row > (max(score_rows[row_group]) + 1):
                    row_group = row
                if row_group not in score_rows:
                    score_rows[row_group] = {}
                score_rows[row_group][row] = value
        col_group = None
        for col in range(e_x):
            value = numpy.mean(npa_im[s_y:e_y, col])
            if color_th[0] <= value <= color_th[1]:
                if col_group is None or col > (max(score_cols[col_group]) + 1):
                    col_group = col
                if col_group not in score_cols:
                    score_cols[col_group] = {}
                score_cols[col_group][col] = value
        if e_y not in score_rows:
            score_rows[e_y] = {e_y: 0}
        if e_x not in score_cols:
            score_cols[e_x] = {e_x: 0}
        # now clean some using accuracy size
        score_rows, score_cols = self._remove_group_under_accuracy_size(score_rows, score_cols, accuracy)
        # generate scan file for debug
        self._save_debug_scanning_results(name, im_src, score_rows, score_cols)
        areas = (len(score_rows) - 1) * (len(score_cols) - 1)
        fully_locked = im_src.size == (max(score_cols) + 1, max(score_rows) + 1)
        self.logger.debug(
            f"areas={areas} - image_locked={fully_locked}:\nrows({len(score_rows)}): {score_rows}\ncols({len(score_cols)})={score_cols}"
        )
        self.logger.debug(f"{len(score_rows)}{len(score_cols)}")
        return score_rows, score_cols

    def _verify_area_detected_valid(self, im_src, left, up, right, down, min_size):
        """verify area given and return if end area found

        :param im_src: source image of area tom check
        :param left: left coord
        :param up: up coordinate
        :param right: right coordinate
        :param down: down coordinate
        :param min_size:
        :return: final coordinates [left, up, right, down] of area found
        """
        final_coordinates = []
        min_size_w = min_size[0]
        min_size_h = min_size[1]
        im_item = self.extract_from_image(im_src, left, up, right, down)
        bbx_area = self.get_black_box_area(im_item)
        if bbx_area:
            # recenter item by removing BBOX
            im_item_bbx = self.extract_from_image(im_item, bbx_area[0], bbx_area[1], bbx_area[2], bbx_area[3])
            self.close_image(im_item)
            im_item = im_item_bbx
            left, up, right, down = [left + bbx_area[0], up + bbx_area[1], left + bbx_area[2], up + bbx_area[3]]
        area_size = (right - left, down - up)
        if (
            self.get_black_box_area(self.image_difference(im_src, im_item)) is None
            and bbx_area == self.get_black_box_area(im_src)
            and area_size == im_src.size
        ):
            self.logger.info(f"item detected identical to source: x={left},y={up},right={right},down={down} - {im_src.size} - {bbx_area}")
        elif (area_size[0] < min_size_w) or (area_size[1] < min_size_h):
            self.logger.info(f"item smaller than minsize: x={left},y={up},right={right},down={down} - {area_size} - {min_size}")
        else:
            colors = sorted(im_item.getcolors(im_item.size[0] * im_item.size[1]))
            # add test to also skip completely transparent area (empty) as not candidate for a usable itemF
            if len(colors) == 1 and colors[0][1] == self.black_tr_color:
                self.logger.info(f"item detected empty: x={left},y={up},right={right},down={down} - colors={len(colors) > 1}")
            else:
                self.logger.debug(
                    f"item found: x={left},y={up},right={right},down={down} - black_box_area ={bbx_area}, size={im_item.size}"
                )
                final_coordinates = [left, up, right, down]
        self.close_image(im_item)
        return final_coordinates

    def _split_image_in_items_or_areas(self, im_src, filename, min_size, score_rows, score_cols, c_mean):
        """source file split areas according input of transparent color row/column

        :param im_src: image source
        :param filename: used to generate sub area key used in dictionary
        :param min_size: minimum size of item to detect
        :param score_rows: group of adjacent rows TC
        :param score_cols: group of adjacent column TC
        :param c_mean: mean value of TC color
        :return: dict of area images name with image and tuple position: {im0: {'im0': im0, 'pos': [area position], im1: ....}
        """
        item_list = {}
        npa_im = numpy.asarray(im_src)
        i = 0
        list_row_group = list(score_rows.keys())
        list_col_group = list(score_cols.keys())
        last_row_group = list_row_group[0]
        for row_group in list_row_group[1:]:
            last_col_group = list_col_group[0]
            item_found = 0
            for col_group in list_col_group[1:]:
                left2, up2, right2, down2 = self._min_rectangle_from_group(
                    score_rows, score_cols, (last_row_group, last_col_group), (row_group, col_group)
                )
                left = self._check_segment_transparency(npa_im, c_mean, score_cols[last_col_group], (up2, down2), vertical=True)
                if left is None:
                    continue
                right = self._check_segment_transparency(npa_im, c_mean, score_cols[col_group], (up2, down2), vertical=True)
                if right is None:
                    continue
                up = self._check_segment_transparency(npa_im, c_mean, score_rows[last_row_group], (left, right), vertical=False)
                if up is None:
                    continue
                down = self._check_segment_transparency(npa_im, c_mean, score_rows[row_group], (left, right), vertical=False)
                if down is None:
                    continue
                item_found += 1
                right += 1
                down += 1
                verify_item = self._verify_area_detected_valid(im_src, left, up, right, down, min_size)
                if verify_item:
                    name = f"{os.path.splitext(filename)[0]}_item{i}.png"
                    i += 1
                    item_list[name] = {"pos": verify_item}
                last_col_group = col_group
            if not item_found:
                continue
            last_row_group = row_group
        self.logger.debug(f"list item found: {item_list}")
        return item_list

    def _scan_and_split_an_image_in_areas(self, im, filename, accuracy, minsize, c_mean, debug=False):
        """run a scan detection of areas bordered by TC line/col on image and split them

        :param im: image source
        :param filename: name of current file
        :param accuracy: minimum size of group of transparent line to use
        :param minsize: minimum size item for detection
        :param c_mean: transparent color mean value
        :param debug: true/False default False, allows debugging of algorithm behavior
        :return: dict of area images name with image and tuple position: {im0: {'im0': im0, 'pos': [area position], im1: ....}
        """
        self.logger.debug("analysing file: %s" % filename)
        sc_rows, sc_cols = self._scan_image_using_color_reference(
            im, f"{os.path.splitext(filename)[0]}_scan.jpg" if debug else None, accuracy, c_mean
        )
        return self._split_image_in_items_or_areas(im, filename, minsize, sc_rows, sc_cols, c_mean)

    def detect_and_extract_items_in_image(
        self, image_path, force_color=None, accuracy=[12, 1], min_item_size=[8, 8], save_items=False, debug=False, revert_filter=False
    ):
        """this is a generic implementation to detect and extract items/areas in image (meaning areas surrounded by Transparent Color)

        the implementation seek for transparent color and if not will force one or user can force some (see wallpaper example)
        then will split images in areas if it can till it discover a single area no more split-able.
        Choosing force TC: one must check the output image background color to force, just open paint and read it or through PIL.
        Example A&BB black panel is not black but (34, 34, 34), status bar is black with a grey line on top [(0, 0, 0), (57, 57, 57)]
        accuracy is max w,h=(1,1) otherwise it will skip group < w,h lines if u want to get rid of TC lines in between characters strings

        :param image_path: path for the image (png expected or format with transparency support)
        :param force_color: 4 modes [select colors used to be replaced by transparent color black]
        :param accuracy: minimum size of group of transparent line accuracy to use, skip group with less
        :param min_item_size: minim size of item (w, h)
        :param save_items: False by default will just save a PNG of the detected items (useful to extract items for reference)
        :param debug: False by default is to generate scan picture for debug debugging purpose
        :param: revert_filter: revert color transparency appliance
        :return: dict of generated area name with their area position and file name if requested to be saved else None
            {"are0": {"pos": [], "name": "area0.png"}, etc ....}

        example of force_color parameter:
        for example for status bar (0, 0, 0,), (57, 57, 57) or black WPP, (0, 0, 0,), (57, 57, 57)(34, 34, 34) for BB
        - list: [] of color (R, G, B) to use as transparent color
        - up: color (R, G, B) up threshold, to use as transparent color all colors from threshold up to (255, 255, 255)
        - down: color (R, G, B) down threshold, to use as transparent color all colors from threshold down to (0, 0, 0)
        - interval: [C1, C2] 2 color (R, G, B) thresholds, use as transparent color all colors inside both threshold interval

        """
        if not os.path.isfile(image_path) or min(accuracy) < 1 or min(min_item_size) < 4:
            raise ValueError(f"{image_path} does not exist or threshold incorrect {accuracy} < [1,1], {min_item_size} < [4,4]")
        im_base = self.open_image(image_path)
        im_copy = im_base.copy()
        if im_copy.mode != "RGBA":
            im_copy = im_base.convert("RGBA")
        # reduce transparent colors to 1
        tcl = self._analyse_image_colors(im_copy)
        if not tcl and not force_color:
            self.close_image(im_base)
            self.close_image(im_copy)
            raise RuntimeError("no transparent color in image and not given")
        im_temp = self._applies_transparent_colors(im_copy, tcl, force_color, revert_filter)
        self.close_image(im_copy)
        modified_file = f"{os.path.splitext(image_path)[0]}_cropped.png"
        tr_color_mean = numpy.mean(self.black_tr_color)
        item_list = {modified_file: {"im": im_temp, "pos": [0, 0, im_temp.width, im_temp.height]}}
        final_item_list = {}
        file_list = [modified_file]
        while file_list:
            self.logger.debug(f"file_list:{file_list}")
            current_file = file_list.pop(0)
            im_temp = item_list[current_file]["im"]
            new_item_list = self._scan_and_split_an_image_in_areas(im_temp, current_file, accuracy, min_item_size, tr_color_mean, debug)
            if not new_item_list and save_items:
                self.logger.debug(f"save file: {current_file}")
                self.save_image(im_temp, current_file)
            self.close_image(item_list[current_file]["im"])
            item_list[current_file]["im"] = None
            file_list += list(new_item_list.keys())
            if new_item_list:
                for item in new_item_list:
                    item_list[item] = new_item_list[item]
                    item_list[item]["pos"][0] += item_list[current_file]["pos"][0]
                    item_list[item]["pos"][1] += item_list[current_file]["pos"][1]
                    item_list[item]["pos"][2] += item_list[current_file]["pos"][0]
                    item_list[item]["pos"][3] += item_list[current_file]["pos"][1]
                    im_item = self.extract_from_image(
                        im_base, item_list[item]["pos"][0], item_list[item]["pos"][1], item_list[item]["pos"][2], item_list[item]["pos"][3]
                    )
                    item_list[item]["im"] = im_item
            else:
                file_no_ext = os.path.splitext(os.path.basename(current_file))[0]
                item_name = file_no_ext.split("_cropped")
                item_name = file_no_ext if len(item_name) <= 1 or not item_name[-1] else item_name[-1]
                final_item_list[item_name] = {"pos": item_list[current_file]["pos"], "name": None if not save_items else current_file}
        self.close_image(im_base)
        self.logger.info(f"items found:{final_item_list}")
        return final_item_list

    @staticmethod
    def get_list_areas_found(items_dict):
        """get list of areas found from detected item dict or reordered detected item dict

        :items_dict dict of items detected from detect_and_extract_items_in_image or reorder_detection_item_by_areas
        :return: list of areas found
        :rtype: list
        """
        items_keys = items_dict.keys()
        # algorithm assumes sorting needed: generated item names but 1 area only is an exception and return image name as item
        if len(items_dict) < 2:
            return list(items_keys)
        return sorted(set(["_" + k.split("_")[1] for k in items_keys if "_" in k]))

    def reorder_detection_item_dict_by_areas(self, detected_items):
        """reorder dictionary by areas ordered by detection

        :detected_items dict of items detected from detect_and_extract_items_in_image
        :return: dict of reordered by detected areas and containing description of items detected in the area
        :rtype: dict
        """
        # algorithm assumes sorting needed: generated item names but 1 area only is an exception and return image name as item
        if len(detected_items) < 2:
            return detected_items
        list_areas = self.get_list_areas_found(detected_items)
        area_dict = {}
        for area in list_areas:
            for item in detected_items.keys():
                # if item starts with area name like "_item3"
                if item == area:
                    area_dict[area] = detected_items[item]
                elif item.startswith(f"{area}_"):
                    # remove area name
                    sub_item = item.replace(area, "", 1)
                    # are there multiple items in this area ?
                    if len(sub_item) > 0:
                        if area not in area_dict:
                            area_dict[area] = {}
                        area_dict[area][sub_item] = detected_items[item]
                    else:  # else 1 item only
                        area_dict[area] = detected_items[item]
            # if there are still sub item not reordered yet in area then recursively reorder it
            area_dict_areas = self.get_list_areas_found(area_dict[area])
            if area_dict_areas and area_dict_areas != list(area_dict[area].keys()):
                area_dict[area] = self.reorder_detection_item_dict_by_areas(area_dict[area])
        return area_dict

    def get_overall_area_position(self, area, ordered_detection):
        """get overall area rectangle from reordered detected items

        :ordered_detection dict of items detected from reorder_detection_item_by_areas
        :return: area rectangle list (t,l,b,r)
        :rtype: list
        """
        if area not in ordered_detection:
            raise ValueError(f"{area} not in dict")
        # 1 item = area => just return size
        if not self.get_list_areas_found(ordered_detection[area]):
            return ordered_detection[area]["pos"]
        # we have multiple item, first is always "_item0"
        first_item = list(ordered_detection[area].keys())[0]
        pos = ordered_detection[area][first_item]["pos"]
        for item in ordered_detection[area]:
            # if item contains multiple items, then recursively resolve it
            if self.get_list_areas_found(ordered_detection[area][item]):
                pos_to_compare = self.get_overall_area_position(item, ordered_detection[area])
            else:  # else just use item size
                pos_to_compare = ordered_detection[area][item]["pos"]
            # store in pos the biggest size
            pos[0] = pos_to_compare[0] if pos[0] > pos_to_compare[0] else pos[0]
            pos[1] = pos_to_compare[1] if pos[1] > pos_to_compare[1] else pos[1]
            pos[2] = pos_to_compare[2] if pos[2] < pos_to_compare[2] else pos[2]
            pos[3] = pos_to_compare[3] if pos[3] < pos_to_compare[3] else pos[3]
        return pos
