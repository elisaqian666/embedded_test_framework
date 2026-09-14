"""Reusable files workflows through device APIs."""
from ...libs.logging import get_logger, log_operation


class FileService:
    def __init__(self, device, *, channel="files"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def download(self, remote_path, local_path):
        return self.device.download(remote_path, local_path, channel=self.channel)

    @log_operation
    def upload(self, local_path, remote_path):
        return self.device.upload(local_path, remote_path, channel=self.channel)
