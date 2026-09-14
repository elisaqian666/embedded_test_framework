from ..libs.logging import log_operation
from ftplib import FTP
from pathlib import Path

from .transport_base import Transport
from ..libs.errors import TransportError, OperationTimeout, DeviceDisconnected


class FTPTransport(Transport):
    def __init__(self, host, *, port=21, username="anonymous", password="anonymous@", timeout=30.0):
        super().__init__(timeout)
        self.host, self.port = host, port
        self.username, self.password = username, password
        self._client = None

    @log_operation
    def connect(self):
        if self.connected:
            return self
        client = FTP()
        try:
            client.connect(self.host, self.port, timeout=self.timeout)
            client.login(self.username, self.password)
        except TimeoutError as exc:
            client.close()
            raise OperationTimeout("FTP connection timed out") from exc
        except Exception as exc:
            client.close()
            raise TransportError("FTP connection failed") from exc
        self._client, self.connected = client, True
        return self

    @log_operation
    def close(self):
        try:
            if self._client is not None:
                self._client.close()
        finally:
            self._client, self.connected = None, False

    @log_operation
    def download(self, remote_path, local_path):
        self.require_connected()
        try:
            with Path(local_path).open("wb") as stream:
                self._client.retrbinary("RETR " + remote_path, stream.write)
        except TimeoutError as exc:
            raise OperationTimeout("FTP download timed out; local file may be partial") from exc
        except (EOFError, ConnectionError) as exc:
            self.connected = False
            raise DeviceDisconnected("FTP connection lost during download") from exc
        except Exception as exc:
            raise TransportError("FTP download failed; local file may be partial") from exc
        return Path(local_path)

    @log_operation
    def upload(self, local_path, remote_path):
        self.require_connected()
        try:
            with Path(local_path).open("rb") as stream:
                self._client.storbinary("STOR " + remote_path, stream)
        except TimeoutError as exc:
            raise OperationTimeout("FTP upload timed out; remote file may be partial") from exc
        except (EOFError, ConnectionError) as exc:
            self.connected = False
            raise DeviceDisconnected("FTP connection lost during upload") from exc
        except Exception as exc:
            raise TransportError("FTP upload failed; remote file may be partial") from exc
