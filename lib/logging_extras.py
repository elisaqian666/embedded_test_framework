import logging
import os
import re
import sys
from logging import Formatter, StreamHandler

_CONFIG = os.getenv("TESTCONFIG", "")


class LogHandler(StreamHandler):
    def __init__(self, stream=sys.stdout):
        super().__init__(stream)

        default_formatter = Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        self.setFormatter(default_formatter)

    def _call_super_emit(self, record):
        """not so nice to have code for better mocking but no other clear way"""
        super().emit(record)

    def emit(self, record):
        messages = str(record.msg).splitlines()
        args = list(record.args)
        for line in messages:
            record.msg = f"{_CONFIG}: {line}"
            number_of_string_subs = len(re.findall(r"%(\d+\.?\d*|\.\d+)?[diouxXeEfFgGcrsab]", line))
            record.args = tuple(args[:number_of_string_subs])
            args = args[number_of_string_subs:]
            self._call_super_emit(record)

def setup_global_logging(log_level: int = logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not any(isinstance(h, LogHandler) for h in root_logger.handlers):
        handler = LogHandler(sys.stdout)
        root_logger.addHandler(handler)

def ascii_box_render(string_to_frame, padding=0, header=""):
    lines = string_to_frame.splitlines()
    max_line_length = len(max(lines, key=len))
    if len(header) > max_line_length:
        max_line_length = len(header)
    horizontal_filler = "="
    vertical_filler = "|"
    divider = horizontal_filler * (max_line_length + 2 + padding * 2)
    padding_string = " " * padding
    lines = ["{0}{1}{2}{1}{0}".format(vertical_filler, padding_string, line.ljust(max_line_length, " ")) for line in lines]
    lines.insert(0, divider)
    if header:
        header_string = horizontal_filler + header.center(max_line_length, " ") + horizontal_filler
        lines.insert(0, header_string)
        lines.insert(0, divider)
    lines.append(divider + "\n")
    ret_val = "\n" + "\n".join(line for line in lines)
    return ret_val
