"""Purpose: Measure elapsed time for framework operations."""

import time
from decimal import Decimal


class Timer(object):
    """a custom timer object for ou library timeout"""

    def __init__(self, watchtime=0):
        self.__start_time = float(0)
        self.__end_time = float(0)
        self.__watch_time = float(Decimal(watchtime))
        self.reset()

    def reset(self, new_watch_time=None):
        """reset timer object and allow changing watch time seamlessly

        :param new_watch_time: new watch time value to reprogram if needed, default=None keep same watch time
        """
        self.__watch_time = float(Decimal(new_watch_time)) if new_watch_time else self.__watch_time
        self.__start_time = time.time()
        self.__end_time = self.__start_time + self.__watch_time

    @property
    def start_time(self):
        """return start time"""
        return self.__start_time

    @property
    def end_time(self):
        """return end time"""
        return self.__end_time

    @property
    def watch_time(self):
        """return watch time"""
        return self.__watch_time

    @property
    def elapsed_time(self):
        """return elapsed time"""
        return time.time() - self.__start_time

    @property
    def timeout_expired(self):
        """reset timer object"""
        return self.__end_time <= time.time()

    @property
    def remaining_time(self):
        """return remaining time timer object"""
        return self.__end_time - time.time()
