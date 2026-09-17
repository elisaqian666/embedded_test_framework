"""
helper to automate mouse movements and keyboard presses
"""

import ctypes
import logging
import os

import cv2
import numpy as np
from retry import retry

from embedded_framework.configurator.config_labels import LOGGERS
from embedded_framework.helpers.he_image_handling import ImageHelper
from embedded_framework.lib.basic_helper_functions import os_is_linux, os_is_macos, os_is_windows


# noinspection PyMissingOrEmptyDocstring
class IAutoGui(object):
    def get_image_location(self, image_path, use_gray_scale=True):
        raise NotImplementedError

    def click(self, x, y, double_click=False):
        raise NotImplementedError

    def click_image(self, image_path, double_click=False, confidence=0.999):
        raise NotImplementedError

    def right_click(self, x, y, double_click=False):
        raise NotImplementedError

    def right_click_image(self, image_path, double_click=False):
        raise NotImplementedError

    def push_hotkey(self, key):
        raise NotImplementedError

    def push_hotkeys(self, *keys):
        raise NotImplementedError

    def type_keys(self, str_to_type, time_interval=0.2):
        raise NotImplementedError

    def play_recording(self, sikuli_file):
        raise NotImplementedError

    def mouse_move(self, to_x, to_y, time=1):
        raise NotImplementedError

    def mouse_drag(self, to_x, to_y, time, button):
        raise NotImplementedError


class AutoGuiPyautoGUIHelper(IAutoGui):
    """
    a helper object to interact with a GUI this class needs a WindowManager
    """

    def __init__(self):
        self.logger = logging.getLogger(LOGGERS.HELPER)

    def get_image_location(self, image_path, use_gray_scale=True):
        """
        gets the location of a certain image on screen

        :param image_path: full path of the image as a string
        :param use_gray_scale: bool if True image locator will not take into account colors. defaults to True
        :return: tuple of coordinates - left, top, width, height
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        assert os.path.isfile(image_path), "The file is not found please provide a better file location %s" % image_path
        self.logger.info("Getting image location...")
        try:
            return pyautogui.locateOnScreen(image_path, grayscale=use_gray_scale)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def get_image_center_location(self, image_path, use_gray_scale=True, confidence=0.999):
        """
        gets the center coordinates of a certain image on screen

        :param image_path: full path of the image as a string
        :param use_gray_scale: bool if True image locator will not take into account colors. defaults to True
        :param confidence: to specify the accuracy due to negligible-pixel-differences
        :return: tuple of coordinates x, y
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        assert os.path.isfile(image_path), "The file is not found please provide a better file location %s" % image_path
        try:
            self.logger.info("Getting image location...")
            return pyautogui.locateCenterOnScreen(image_path, grayscale=use_gray_scale, confidence=confidence)
        except OSError:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def get_screenshot(self, image_path=None, region=None):
        """get the screenshot computer

        :param image_path: full path of the image as a string to save, default None
        :param region: optional region parameter, default None
        :return: PIL Image of the screen
        :rtype: PIL.Image.Image
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        try:
            self.logger.info("Getting screenshot ...")
            return pyautogui.screenshot(image_path, region)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def click(self, x, y, double_click=False, duration=0):
        """
        mimics a mouse click on given x and y coordinates

        :param double_click: bool to define if double click is asked defaults to False (single click)
        :param x: horizontal axis
        :param y: vertical axis
        :param duration: duration of click
        """
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            self.logger.info(
                "Performing mouse left click (x=%d, y=%d, db_click=%d, duration=%f)..." % (x, y, double_click, float(duration))
            )
            pyautogui.doubleClick(x, y, duration=duration) if double_click else pyautogui.click(x, y, duration=duration)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def click_image(self, image_path, double_click=False, confidence=0.999):
        """
        clicks in the middle of the given image if found on screen, if image not found raises a custom Exception

        :param double_click: bool to define if double click is asked defaults to False (single click)
        :param image_path: full file path of the image which will be matched with the opened image
        :param confidence: to specify the accuracy due to negligible-pixel-differences
        """
        image_list = []
        if os.path.isdir(image_path):
            self.logger.debug(image_path + "is a directory, scanning for images....")
            self.logger.debug("found this list of files " + str(os.listdir(image_path)))
            for image in os.listdir(image_path):
                full_path = image_path + os.sep + image
                # self.logger.debug('checking if ' + full_path + ' is an image')
                if os.path.isfile(full_path):
                    # self.logger.debug('checking if ' + full_path + ' is an image')
                    if (
                        "jpg" in full_path.lower()
                        or "jpeg" in full_path.lower()
                        or "png" in full_path.lower()
                        or "bmp" in full_path.lower()
                    ):
                        image_list.append(full_path)
        elif os.path.isfile(image_path):
            image_list = [image_path]
        else:
            raise AssertionError("The file is not found please provide a better file location %s" % image_path)
        self.logger.debug(image_list)

        for image_full_path in image_list:
            image_location = self.get_image_center_location(image_full_path, confidence=confidence)
            if image_location is None:
                self.logger.debug(str(image_full_path) + " not found ")
            else:
                self.logger.info("Getting center location of image...")
                center_x, center_y = image_location  # extract center coordinates of image
                self.logger.info("Performing " + ["", " double "][double_click] + "click ...")
                self.click(center_x, center_y, double_click)
                return None
        raise ImageNotFoundErr

    def right_click(self, x, y, double_click=False, duration=0):
        """
        mimics a right mouse click on given x and y coordinates

        :param double_click: bool to define if double click is asked defaults to False (single click)
        :param x: horizontal axis
        :param y: vertical axis
        :param duration: duration of click
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        try:
            if double_click:
                self.logger.info("Performing right double click(x=%d, y=%d)..." % (x, y))
                pyautogui.click(x, y, clicks=2, button="right", duration=duration)  # Another way to mimic double click
            else:
                self.logger.info("Performing right click(x=%d, y=%d)..." % (x, y))
                pyautogui.click(x, y, button="right", duration=duration)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def right_click_image(self, image_path, double_click=False):
        """
        right clicks in the middle of the given image if found on screen, if image not found raises a custom Exception

        :param double_click: bool to define if double click is asked defaults to False (single click)
        :param image_path: full filepath of the image to click on
        """
        image_location = self.get_image_center_location(image_path)
        if image_location is None:
            raise ImageNotFoundErr
        else:
            self.logger.info("Right clicking image...")
            x, y = image_location
            self.right_click(x, y, double_click)

    def push_hotkey(self, key):
        """
        pushes and releases a keyboard key

        :param key: the keyboard key
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        if key in pyautogui.KEYBOARD_KEYS:
            self.logger.info("Pressing %s key", key)
            try:
                pyautogui.press(key)
            except:
                self.logger.debug(ctypes.get_errno(), exc_info=True)
        else:
            raise InvalidKeyErr

    def push_hotkeys(self, *keys):
        """
        pushes and releases a combination of keyboard keys at the same time

        :param keys: the keyboard keys as a tuple
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        for key in keys:
            if key not in pyautogui.KEYBOARD_KEYS:
                raise InvalidKeyErr
        self.logger.info("Pressing: %s", str(keys))
        try:
            pyautogui.hotkey(*keys)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def type_keys(self, str_to_type, time_interval=0.2):
        """
        types the given string as if someone was typing it

        :param time_interval: time in between keypresses
        :param str_to_type: string to type
        """
        self.logger.info("Typing string: %s", str_to_type)
        import pyautogui

        pyautogui.FAILSAFE = False
        try:
            pyautogui.typewrite(str_to_type, interval=time_interval)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def key_up(self, key):
        """
        Function to release a key

        :param key: What key to release
        """
        self.logger.info("Releasing %s key", key)
        import pyautogui

        pyautogui.FAILSAFE = False
        try:
            pyautogui.keyUp(key)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def key_down(self, key):
        """
        Function to press down a key

        :param key: What key to press down
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        self.logger.info("Pressing %s key", key)
        try:
            pyautogui.keyDown(key)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    @retry(tries=2, delay=1)
    def mouse_move(self, to_x, to_y, duration=1):
        """
        move the mouse pointer from one point to another the action will take time time

        :param to_x: what is horizontal position to move to
        :param to_y: what is vertical position to move to
        :param duration: how long the movement should take
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        # Check if the coordinates are present on screen
        try:
            if pyautogui.onScreen(to_x, to_y):
                self.logger.info("Moving to coordinates: %s, %s", to_x, to_y)
                pyautogui.moveTo(to_x, to_y, duration=duration)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)
            raise

    def mouse_drag(self, to_x, to_y, time, button="left"):
        """
        drag the mouse pointer to location given

        :param to_x: drag mouse to this location on x coordinate
        :param to_y: drag mouse to this location on y coordinate
        :param button: left click/ right click/ middle click
        :param time: drag the mouse pointer over a period of 'time' time.
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        self.logger.info("Dragging mouse pointer to %s, %s location...", to_x, to_y)
        try:
            pyautogui.dragTo(to_x, to_y, duration=time, button=button)
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    @retry(tries=2, delay=1)
    def get_cursor_position(self):
        """
        Get the current mouse cursor position

        :return: x,y coordinates of mouse cursor
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        self.logger.info("Getting current location of mouse cursor...")
        try:
            return pyautogui.position()
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    @retry(tries=2, delay=1)
    def get_screen_size(self):
        """
        Get screen height, width of monitor

        :return: screen height and width as tuple
        """
        import pyautogui

        pyautogui.FAILSAFE = False
        self.logger.info("Getting screen size...")
        try:
            ret = pyautogui.size()
        except:
            self.logger.debug(ctypes.get_errno(), exc_info=True)

    def minimize_all_windows(self):
        """
        Minimize all application windows

        :raises OSError: if OS is not MacOS or Windows, then it raises OSError
        """
        if os_is_windows():
            self.push_hotkeys("winleft", "d")
        elif os_is_macos():
            self.push_hotkeys("command", "option", "h", "m")
        else:
            raise OSError("This method only support Windows and MacOS.")

    def minimize_top_most_window(self):
        """minimize top most window"""
        if os_is_windows():
            self.push_hotkeys("alt", "space", "n")
        elif os_is_macos() or os_is_linux():
            self.push_hotkeys("command", "m")

    def switch_focus_window(self):
        """switch the focus window"""
        if os_is_windows():
            self.push_hotkeys("alt", "tab")
        elif os_is_macos() or os_is_linux():
            self.push_hotkeys("command", "tab")

    def get_list_currently_open_windows_information(self):
        """get list of windows open

        :return: list of win object: <Win32Window left="0", top="0", width="1920", height="1080", title="Program Manager">
        """
        if os_is_windows():
            import pyautogui

            pyautogui.FAILSAFE = False
            self.logger.info("Getting list of open windows")
            try:
                return pyautogui.getAllWindows()
            except:
                self.logger.debug(ctypes.WinError())
        else:
            raise OSError("This method only supported on Windows.")

    def detect_cursor_at_position(self, x, y, screenshot_path, desktop_resolution, crop_output_path=None, threshold=0.6):
        """
        Detect Windows mouse pointer at a given position by analyzing a screenshot.
        Loads screenshot from path, crops around current mouse location on desktop, and detects cursor.
        Uses desktop vs screenshot resolution scaling to ensure location accuracy.

        :param x: X coordinate on desktop where cursor should be
        :param y: Y coordinate on desktop where cursor should be
        :param screenshot_path: Path to screenshot image file
        :param desktop_resolution: Tuple of (width, height) of desktop
        :param crop_output_path: Optional path to save cropped cursor region for debugging
        :param threshold: Confidence threshold for cursor detection (0.0-1.0, default 0.6)
        :return: Tuple of (cursor_found, confidence_score, cursor_location_in_crop)
        """
        # Cursor detection constants
        CROP_RADIUS = 100  # How much to crop around the cursor position
        CURSOR_BRIGHT_THRESHOLD = 250  # Threshold for bright part of cursor
        CURSOR_DARK_THRESHOLD = 5  # Threshold for dark part of cursor
        CURSOR_MIN_AREA = 1  # Minimum area of detected contour to be considered cursor
        CURSOR_MAX_AREA = 300  # Maximum area of detected contour to be considered cursor
        CURSOR_MIN_ASPECT_RATIO = 1.2  # Minimum aspect ratio (elongation) of cursor
        CURSOR_BORDER_MARGIN = 2  # Margin from border to ignore contours touching edges
        IDEAL_AREA = (CURSOR_MIN_AREA + CURSOR_MAX_AREA) / 2  # Ideal area for confidence calculation
        IDEAL_ASPECT = CURSOR_MIN_ASPECT_RATIO * 1.5  # Ideal aspect ratio for confidence calculation

        # Get desktop and screenshot dimensions
        desktop_width, desktop_height = desktop_resolution

        # Load screenshot image from base unit
        image_helper = ImageHelper()
        screenshot_image = image_helper.open_image(screenshot_path)
        screenshot_width, screenshot_height = screenshot_image.size

        # Scale mouse coordinates to screenshot resolution
        scale_x = screenshot_width / desktop_width
        scale_y = screenshot_height / desktop_height
        scaled_x = int(x * scale_x)
        scaled_y = int(y * scale_y)

        self.logger.info(f"Desktop resolution: {desktop_width}x{desktop_height}")
        self.logger.info(f"Screenshot resolution: {screenshot_width}x{screenshot_height}")
        self.logger.info(f"Original position: ({x}, {y}), Scaled position: ({scaled_x}, {scaled_y})")

        # Extract crop region around cursor
        crop_image = image_helper.extract_from_image(
            screenshot_image, scaled_x - CROP_RADIUS, scaled_y - CROP_RADIUS, scaled_x + CROP_RADIUS, scaled_y + CROP_RADIUS
        )

        # Save cropped image for debugging if path provided
        if crop_output_path:
            image_helper.save_image(crop_image, crop_output_path)
            self.logger.info(f"Saved cropped cursor region to: {crop_output_path}")

        # Convert PIL Image to OpenCV format for cursor detection
        img = cv2.cvtColor(np.array(crop_image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        best_score = 0.0
        best_loc = None

        # Try both bright and dark thresholds to detect cursor
        threshold_configs = [
            ("bright", cv2.threshold(gray, CURSOR_BRIGHT_THRESHOLD, 255, cv2.THRESH_BINARY)[1]),
            ("dark", cv2.threshold(gray, CURSOR_DARK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]),
        ]

        for thresh_type, thresh in threshold_configs:
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                cx, cy, w, h = cv2.boundingRect(cnt)
                aspect = max(h / w, w / h) if w > 0 else 0

                # Cursor checks: correct size, elongated shape, not touching borders
                if (
                    CURSOR_MIN_AREA <= area <= CURSOR_MAX_AREA
                    and aspect >= CURSOR_MIN_ASPECT_RATIO
                    and CURSOR_BORDER_MARGIN < cx < gray.shape[1] - CURSOR_BORDER_MARGIN
                    and CURSOR_BORDER_MARGIN < cy < gray.shape[0] - CURSOR_BORDER_MARGIN
                ):
                    # Calculate confidence using detection parameters
                    area_score = 1.0 - abs(area - IDEAL_AREA) / CURSOR_MAX_AREA
                    aspect_score = 1.0 - abs(aspect - IDEAL_ASPECT) / IDEAL_ASPECT
                    # Position score: distance from center (normalized)
                    center_x, center_y = cx + w // 2, cy + h // 2
                    img_center_x, img_center_y = gray.shape[1] // 2, gray.shape[0] // 2
                    distance_from_center = np.hypot(center_x - img_center_x, center_y - img_center_y)
                    max_distance = np.hypot(img_center_x, img_center_y)
                    position_score = 1.0 - distance_from_center / max_distance
                    score = (area_score + aspect_score + position_score) / 3.0
                    if score > best_score:
                        best_score = score
                        best_loc = (center_x, center_y)
                        self.logger.info(
                            f"Cursor candidate (bright): area={area_score:.2f}, aspect={aspect_score:.2f}, "
                            f"pos={position_score:.2f}, score={score:.3f}"
                        )

        cursor_found = best_score >= threshold
        self.logger.info(f"Cursor detection result: found={cursor_found}, confidence={best_score:.2f}, location={best_loc}")

        return cursor_found, best_score, best_loc


class ImageNotFoundErr(Exception):
    pass


class InvalidKeyErr(Exception):
    pass
