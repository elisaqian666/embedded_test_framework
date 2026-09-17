"""Purpose: Provide product-independent FTP and FTPS communication."""

import contextlib
import ftplib
import logging
import os
import re
import ssl
import time
from collections import namedtuple
from datetime import datetime
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from embedded_framework.lib import timeout
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException


class FailedToChangeWorkingDirectoryError(EmbeddedFrameworkException): ...


class FtpEngine:
    def __init__(self, session: ftplib.FTP, hostname, username, password, port, protocol="ftp"):
        self.__ftp_session = session
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.protocol = protocol
        self.logger = logging.getLogger("ftp")
        self.logger.info("created an ftp engine to %s with username %s", str(hostname), str(username))
        self._root_dir = None

    def __repr__(self):
        return f"{self.__class__.__name__}(hostname={self.hostname!r}, username={self.username!r}, port={self.port}, protocol={self.protocol!r})"

    def close(self) -> None:
        """Release the FTP transport without requiring a responsive server."""
        if self.__ftp_session is not None:
            self.__ftp_session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self):
        try:
            session = self.__ftp_session
            if session is not None:
                session.close()
        except Exception:
            pass
        finally:
            self.__ftp_session = None

    @contextlib.contextmanager
    def _ftp_connect(self, error_message="FTP connect error", custom_exception_cls=EmbeddedFrameworkException):
        try:
            self._connect()
            yield
        except ftplib.all_errors as e:
            self.close_ftp_session()
            msg = f"{error_message} for {self}. The FTP session is closed."

            raise custom_exception_cls(msg) from e

    @staticmethod
    def _get_datetime_from_ftp_list_date(year_or_time, month_abbr, day):
        """
        Return datetime object based on the date part of a line from the ftp LIST command output.

        :param year_or_time: year or time part of the date
        :type year_or_time: str
        :param month_abbr: month abbreviation
        :type month_abbr: str
        :param day: day part of the date
        :type day: str
        :return: datetime object
        :rtype: datetime
        """
        month = time.strptime(month_abbr, "%b").tm_mon
        # If time is present (e.g., "Jul 16 19:14" instead of "Jul 16 2025"), infer the year.
        # Use current year, but if that results in a future datetime, roll back to last year.
        if ":" in year_or_time:
            hour, minutes = year_or_time.split(":")
            now = datetime.now()
            dt = datetime(now.year, int(month), int(day), int(hour), int(minutes))
            if dt > now:
                dt = dt.replace(year=now.year - 1)
            return dt

        # If an explicit year is present (e.g., "Feb 14  2025"), use it directly.
        year = int(year_or_time)
        return datetime(year, int(month), int(day), 0, 0)

    @cached_property
    def _supported_commands(self) -> tuple:
        """
        Get the list of supported commands by the FTP server.

        return: tuple of supported commands
        rtype: tuple
        """
        with self._ftp_connect("Failed to get supported commands from FTP server"):
            response = self.__ftp_session.sendcmd("HELP")
        commands = re.findall(r"\b[A-Z]{3,4}\b", response)
        return tuple(commands)

    def __protocol__(self):
        return self.protocol

    def _connect(self):
        """
        connect to the FTP server. It handles below types of exception,

        1. 10053 - FTP timeout error
        2. 530 - login error
        3. AttributeError : FTP quit error
        """
        cur_dir = None
        try:
            self.logger.debug("checking connection")

            cur_dir = self.__ftp_session.pwd()
        except ssl.SSLError:
            self.logger.debug("SSL error occurred while FTP session closed by the server because of server timeout", exc_info=True)
            self._connect_and_login_to_session()
        except ftplib.all_errors as excp:
            self.logger.debug("FTP Exception", exc_info=True)
            if (
                "10053" in str(excp)
                or "530" in str(excp)
                or "421" in str(excp)
                or "10054" in str(excp)
                or "[SSL: WRONG_VERSION_NUMBER]" in str(excp)
            ):
                self._connect_and_login_to_session()
            else:
                raise
        except AttributeError:
            self.logger.debug("Attribute Exception when FTP connection is already closed", exc_info=True)
            self._connect_and_login_to_session()

        if self._root_dir is None:
            if not cur_dir:
                cur_dir = self.__ftp_session.pwd()
            self._root_dir = cur_dir

    def _connect_and_login_to_session(self):
        self.logger.info(f"Connecting to FTP and login with {self.username}...")
        self.__ftp_session.connect(self.hostname, self.port, timeout=self.__ftp_session.timeout)
        self.__ftp_session.login(self.username, self.password)
        if self.protocol == "ftps":
            self.__ftp_session.prot_p()
        self.logger.info("Connection with ftp server established")

    def __str__(self):
        return (
            "Running FTP engine on "
            + str(self.hostname)
            + " with username:"
            + str(self.username)
            + " and password:"
            + "********"
            + " on port:"
            + str(self.port)
        )

    def download(self, remote_path, file_name, local_dir=os.getcwd(), local_file=None):
        """
        gets a file or a complete directory from a server to a local_dir

        :param local_file:
        :param remote_path: the remote directory as a string
        :param file_name: the filename as a string
        :param local_dir: the local directory to store the file to defaults to working dir
        :rtype: str
        """
        self._connect()
        self.cwd(remote_path)
        file_retr = f"RETR {file_name}"
        if not local_file:
            local_file = file_name
        retry_counter = 0
        new_file = os.path.join(local_dir, local_file)
        self.logger.info("new file path will be %s", str(new_file))
        try:
            while retry_counter < 2:
                self.logger.warning("try %d" % retry_counter)
                self._remove_file_if_exists(new_file)
                self._retrieve_binary_to_local_file(file_name, file_retr, new_file)
                time.sleep(5)
                if self.__ftp_session.size(file_name) == int(os.path.getsize(new_file)):
                    self.logger.info("file downloaded successfully..")
                    break
                else:
                    self.logger.warning("something went wrong, source and destination file are not the same, will now retry once")

                    retry_counter += 1
            if retry_counter >= 2:
            raise EmbeddedFrameworkException("Too many retries, file size of source and destination never matched")

        except Exception as excep:
            self.logger.error(excep)
            self._remove_file_if_exists(new_file)
            self.close_ftp_session()
            raise EmbeddedFrameworkException() from excep
        self.cwd(self._root_dir)
        return new_file

    def download_tree(self, ftp_path, local_path=os.getcwd(), pattern=None, overwrite=False):
        """
        Downloads an entire directory tree from an ftp server to the local destination

        :param ftp_path: the folder on the ftp server to download
        :type ftp_path: str
        :param local_path: the local directory to store the copied folder
        :type local_path: str
        :param pattern: Python regex pattern, only files that match this pattern will be downloaded.
        :type pattern: str
        :param overwrite: set to True to force re-download of all files, even if they appear to exist already
        :type overwrite: bool

        :return: Full local absolute path
        :rtype: str

        :Example:

        >>> ftp_engine.download_tree(r"/Software/trunk", r"D:\temp")
        """
        self._connect()
        file_name = os.path.basename(ftp_path)
        file_path = os.path.join(local_path, file_name)

        if self.is_path_a_directory(ftp_path):
            self._download_ftp_dir(
                ftp_path,
                file_path,
                pattern=pattern,
                overwrite=overwrite,
            )
        else:
            file_retr = f"RETR {ftp_path}"
            if not os.path.exists(file_path) or overwrite is True:
                self._retrieve_binary_to_local_file(file_name, file_retr, file_path)

        return os.path.abspath(file_path)

    def close_ftp_session(self):
        """
        closes the ftp session
        """
        with contextlib.suppress(AttributeError):
            self.logger.info("closing ftp session")
            self.__ftp_session.quit()

    def _retrieve_binary_to_local_file(self, file_name, file_retr, new_file):
        with open(new_file, "wb") as file_n:
            self.logger.info("fetching and saving binary to %s at %s", file_name, new_file)
            try:
                self.__ftp_session.retrbinary(file_retr, file_n.write, blocksize=32768)
            except ftplib.all_errors as excep:
                self.logger.error("caught an exception %s", str(excep))
                file_n.close()
            raise EmbeddedFrameworkException from excep

    def _remove_file_if_exists(self, new_file):
        if os.path.exists(new_file):
            self.logger.info("file %s already present on location, will remove!!", str(new_file))
            timeout.wait_no_exception_timeout(os.remove, 20, Exception, new_file)

    def upload(self, file_to_upload, ftp_path):
        """
        puts a file to the ftp location

        :param file_to_upload: path to the local_file
        :param ftp_path: path for uploading into FTP
        :return: boolean
        """
        self._connect()
        self.logger.info("Remote Path: %s", ftp_path)
        self.logger.info("Local file: %s", file_to_upload)
        if ftp_path.startswith("/"):
            ftp_path = ftp_path[1:]
        if not ftp_path.endswith("/"):
            ftp_path += "/"

        self.__ftp_session.cwd(ftp_path)
        status = False
        if os.path.isdir(file_to_upload):
            base_name = os.path.basename(file_to_upload)
            self.logger.info("Creating directory %s", base_name)
            self.__ftp_session.mkd(base_name)
            for elem in os.listdir(file_to_upload):
                self.upload(os.path.join(file_to_upload, elem), ftp_path + base_name)
            return
        self.logger.info("copying %s", file_to_upload)
        with open(file_to_upload, "rb") as my_file:
            remote_file = ftp_path + os.path.basename(file_to_upload)
            self.logger.info("remote file %s", remote_file)
            self.__ftp_session.storbinary(f"STOR {os.path.basename(file_to_upload)}", my_file, 1024)

            self._connect()
            if self.__ftp_session.size(os.path.basename(file_to_upload)) == os.path.getsize(file_to_upload):
                status = True
            my_file.close()
        self.cwd(self._root_dir)
        return status

    def upload_directory_contents(self, path_to_upload, ftp_path):
        """
        puts the contents of a directory to the ftp location

        :param path_to_upload: path to the local directory
        :param ftp_path: path for uploading into FTP
        """
        if not os.path.isdir(path_to_upload):
            raise NotADirectoryError("The path to upload was not a directory")

        self._connect()

        self.cwd(ftp_path)
        self.logger.info("Remote Path: %s", ftp_path)
        self.logger.info("Local file: %s", path_to_upload)

        self._upload_full_path_w_recursion(path_to_upload)
        self.cwd(self._root_dir)

    def upload_directory(self, path_to_upload, ftp_path):
        """
        puts a directory to the ftp location

        :param path_to_upload: path to the local directory
        :param ftp_path: path for uploading into FTP
        """
        if not os.path.isdir(path_to_upload):
            raise NotADirectoryError("The path to upload was not a directory")

        self._connect()

        self.cwd(ftp_path)
        self.logger.info("Remote Path: %s", ftp_path)
        self.logger.info("Local file: %s", path_to_upload)

        base_name = os.path.basename(path_to_upload)
        self.logger.info("Creating directory %s", base_name)
        self.__ftp_session.mkd(base_name)
        if not ftp_path.endswith("/"):
            ftp_path += "/"
        ftp_path = ftp_path + base_name

        self.upload_directory_contents(path_to_upload, ftp_path)

    def _upload_full_path_w_recursion(self, local_path_to_upload):
        for name in os.listdir(local_path_to_upload):
            local_path = os.path.join(local_path_to_upload, name)
            if os.path.isfile(local_path):
                try:
                    self.logger.debug("STOR %s %s", str(name), str(local_path))
                    with open(local_path, "rb") as f:
                        self.__ftp_session.storbinary(f"STOR {name}", f, blocksize=32768)
                except Exception as e:
                    self.logger.error("Encountered exception: %s while trying to upload file %s. \nRetrying...", str(e), str(local_path))
                    self._connect()
                    with open(local_path, "rb") as f:
                        self.__ftp_session.storbinary(f"STOR {name}", f, blocksize=32768)
            elif os.path.isdir(local_path):
                self.logger.debug("MKD %s", str(name))
                self.make_ftp_directory_if_not_exists(name)
                self.logger.debug("CWD %s", str(name))
                self.__ftp_session.cwd(name)
                self._upload_full_path_w_recursion(local_path)
                self.logger.debug("CWD ..")
                self.__ftp_session.cwd("..")

    def make_ftp_directory_if_not_exists(self, name):
        self._connect()
        try:
            self.__ftp_session.mkd(name)

        # ignore "directory already exists"
        except ftplib.error_perm as e:
            if "550" not in str(e):
                raise

    def cwd(self, remote_path):
        remote_path = remote_path.replace("\\", "/")
        remote_path = (Path("/") / Path(remote_path)).as_posix()

        self.logger.info("Change working directory to %s", remote_path)
        error_msg = f"Failed to change current working directory to {remote_path}"
        with self._ftp_connect(error_msg, custom_exception_cls=FailedToChangeWorkingDirectoryError):
            self.__ftp_session.cwd(remote_path)

    def return_sorted_dirs_by_modified_date(self, remote_path):
        """
        function to sort ftp directories based on modified date from oldest to newest

        :param remote_path: remote path
        :return: a list with sorted tuples, consisting in  modified date and dir name, by modified date from oldest to newest
        """
        dir_dict = self.return_dir_contents_as_dict(remote_path)
        date_and_dir = []
        for dir_name, info in dir_dict.items():
            if info.get("type") != "dir":
                continue
            modify_str = info.get("modify")
            try:
                t_struct = time.strptime(modify_str, "%Y%m%d%H%M%S")
            except Exception as e:
                self.logger.warning(f"Failed to parse {modify_str} for {dir_name}: {e}")
                continue
            date_and_dir.append((t_struct, dir_name))
        return sorted(date_and_dir, key=lambda tup: tup[0])

    def return_list_dirs_sorted_alphabetically(self, remote_path):
        """
        :param remote_path: the remote path
        :return: list of directory names sorted alphabetically
        :rtype: list
        """
        dir_contents = self.return_dir_contents_as_dict(remote_path)
        return sorted(name for name, props in dir_contents.items() if props.get("type") == "dir")

    def return_dir_contents_as_dict(self, remote_path, sort_on=None, desc=False):
        """
        Get directory contents as a dictionary. The key is the file name and the value is the file properties.

        The properties are the same as the output of the ``mlsd`` command (``type``, ``unix.mode``, ``size``, etc.).

        Example::

            {
                "Software": {
                    "modify": "20250121110328",
                    "type": "dir",
                    "unique": "29U100",
                    "size": "242",
                    "unix.mode": "0777",
                    "unix.owner": "root",
                    "unix.group": "root",
                },
                ...
            }

        Note that the "unique" property is not available on servers that do not support the MLSD command.

        :param remote_path: the remote path
        :type remote_path: str
        :param sort_on: the key to sort the dictionary by. Sort by filename if not specified.
        :type sort_on: str
        :param desc: set to True to sort in descending order. Defaults to False (= Ascending).
        :type desc: bool
        :return: returns a dict of all contents and its properties of the given path on the ftp server
        :rtype: dict
        """
        if "MLSD" in self._supported_commands:
            dir_data = self._return_dir_contents_as_dict_using_mlsd(remote_path)
        else:  # Fallback to LIST command
            dir_data = self._return_dir_contents_as_dict_using_list(remote_path)
        dir_data.sort(sort_on=sort_on, desc=desc)
        return dir_data

    def _return_dir_contents_as_dict_using_mlsd(self, remote_path):
        """
        :param remote_path: the remote path
        :type remote_path: str
        :return: returns a dict of all contents and its properties of the given path on the ftp server
        :rtype: dict
        """
        with self._ftp_connect("Failed to get directory contents from FTP server"):
            dir_data = self.__ftp_session.mlsd(remote_path)
        return DirData(dir_data)

    def _return_dir_contents_as_dict_using_list(self, remote_path):
        """
        Parse the ooutput of the LIST command to look like the output of the MLSD command

        AFAIK the "unique" value returned by MLSD cannot be retrieved in any way on a server that doesn't supports MLSD. So, an empty string
        will be returned for the "unique" key.
        The ftp LIST command returns less detail in the timestamp than MLSD command. If an entry is more than a year old only the date is
        present, so the return value would be for instance be "20210121110328" with MLSD and "20210121000000" with LIST

        :param remote_path: the remote path
        :type remote_path: str
        :return: returns a dict of all contents and its properties of the given path on the ftp server
        :rtype: dict
        """
        re_listline_properties = re.compile(
            r"^(?P<type>[-d])(?P<permissions>[rwx-]{9})\s+\d+\s+"  # e.g. "drwxr-xr-x 2". The digit is the number of links and is ignored
            r"(?P<owner>\S+)\s+(?P<group>\S+)\s+"  # e.g. "root root" or "1000 1000"
            r"(?P<size>\d+)\s+"
            r"(?P<month>[A-Z][A-Za-z]{2})\s+(?P<day>\d{1,2})\s+(?P<year_or_time>\d{2}:?\d{2})\s+"  # e.g. 2024 or 12:34
            r'(?P<filename>[^<>:"/\\|?*]+?)$'  # <= not any character that is invalid in Windows, Linux and/or macOS file paths
        )
        dir_data = DirData()
        dir_listing = []
        with self._ftp_connect("Failed to get directory contents from FTP server"):
            self.__ftp_session.dir(remote_path, dir_listing.append)
            if not dir_listing:
                return dir_data
            for line in dir_listing:
                path_properties = {}
                match = re_listline_properties.match(line)
                if match:
                    path_properties["type"] = "dir" if match.group("type") == "d" else "file"
                    binary = "".join(["1" if c != "-" else "0" for c in match.group("permissions")])  # e.g. 'rwxr-xr-x' -> '111101101'
                    path_properties["unix.mode"] = f"0{oct(int(binary, 2))[2:]}"  # e.g. '111101101' -> '0755'
                    path_properties["unix.owner"] = match.group("owner")
                    path_properties["unix.group"] = match.group("group")
                    path_properties["size"] = match.group("size")
                    dt = self._get_datetime_from_ftp_list_date(match.group("year_or_time"), match.group("month"), match.group("day"))
                    path_properties["modify"] = dt.strftime("%Y%m%d%H%M%S")
                    path_properties["unique"] = ""
                    dir_data[match.group("filename")] = path_properties
        return dir_data

    def return_file_list(self, remote_folder_path=None):
        """
        :param remote_folder_path: the remote folder path
        :return: returns a list of filename under the folder
        :rtype: list
        """
        self._connect()
        try:
            if remote_folder_path:
                self.logger.info("Getting files from folder under %s", remote_folder_path)
                self.__ftp_session.cwd(remote_folder_path)
            files = []
            self.__ftp_session.dir(files.append)
            self.cwd(self._root_dir)
        except ftplib.all_errors as err:
            self.logger.error(str(err))
            self.close_ftp_session()
            raise
        return files

    def is_file_present(self, remote_folder, filename):
        """
        Checks if 'filename' is present under 'remote_folder'.

        Uses MLSD when the server supports it, falling back to the LIST command.
        Both paths handle filenames that contain spaces.

        :param filename: search file name
        :param remote_folder: FTP path
        :rtype: bool
        """
        dir_contents = self.return_dir_contents_as_dict(remote_folder)
        self.logger.info("Directory contents: %s", list(dir_contents))
        return filename in dir_contents and dir_contents[filename].get("type") != "dir"

    def is_path_present(self, path):
        """
        Checks if path is present.

        e.g. :
        - path = "/Software/non_existent_folder" => False
        - path = "/Software/existent_folder" => True
        - path = "/Software/existent_folder/non_existing_file" => False
        - path = "/Software/non_existent_folder/non_existing_file" => False
        - path = "/Software/existing_folder/existing_file" => True

        :param path: A path on FTP server
        :type path: str
        :rtype: bool
        """

        path = PurePosixPath(path)
        if self.is_path_a_directory(str(path)):
            return True
        else:
            parent_dir = str(path.parent)
            if self.is_path_a_directory(parent_dir):
                return self.is_file_present(parent_dir, path.name)
            return False

    def get_file_size(self, remote_path, filename=None):
        """
        Returns the filesize of the file 'remote_path/filename', or if filename is None, returns the total size of all files under 'remote_path' (directory).

        :param remote_path: FTP path
        :param filename: file name, or None to compute size of all files under remote_path
        :rtype: int
        """
        TYPE_BINARY_CMD = "TYPE i"
        LOG_TYPE_BINARY = "setting type to binary"

        self._connect()
        if filename is not None:
            size = self.__get_single_file_size(remote_path, filename, TYPE_BINARY_CMD, LOG_TYPE_BINARY)
        else:
            size = self.__get_directory_size(PurePosixPath(remote_path), TYPE_BINARY_CMD, LOG_TYPE_BINARY)
        return size if size else 0

    def __get_single_file_size(self, remote_path, filename, type_binary_cmd, log_type_binary):
        if not self.is_file_present(remote_path, filename):
            self.logger.error("%s not found under %s", filename, remote_path)
            return None
        self.cwd(remote_path)
        self.logger.info(log_type_binary)
        self.__ftp_session.sendcmd(type_binary_cmd)
        try:
            size = self.__ftp_session.size(filename)
        except Exception as e:
            self.logger.error(f"Failed to get the file size for {remote_path}/{filename}: {str(e)}")
            size = 0
        self.cwd(self._root_dir)
        return size

    def __get_directory_size(self, path, type_binary_cmd, log_type_binary):
        if not self.is_path_a_directory(path.as_posix()):
            self.logger.error("%s is not a directory", path.as_posix())
            return None
        total_size = 0
        self._connect()
        self.cwd(path.as_posix())
        for entry_name, facts in self.__ftp_session.mlsd():
            entry_type = facts.get("type")
            if entry_type == "dir":
                dir_size = self.get_file_size((path / entry_name).as_posix())
                if dir_size:
                    total_size += dir_size
            elif entry_type == "file":
                self.logger.info(log_type_binary)
                self.__ftp_session.sendcmd(type_binary_cmd)
                try:
                    file_size = self.__ftp_session.size(entry_name)
                    if file_size:
                        total_size += int(file_size)
                except Exception as e:
                    self.logger.error(f"Failed to get the file size for {(path / entry_name).as_posix()}: {str(e)}")
        self.__ftp_session.cwd("..")
        return total_size

    def get_file_list_with_modified_date(self, remote_folder_path) -> list[NamedTuple]:
        """
        Get the modified date of files and folders which is present under 'remote_folder_path'

        :param remote_folder_path: FTP path
        :type remote_folder_path: str
        :return: list of :py:class:`NamedTuple` which holds the filename, modified date, and is a folder or not
        :rtype: list[NamedTuple]
        """

        data_info = namedtuple("file_info", ["file_path", "modified_date", "is_folder"])

        def get_path_properties(file_or_folder_info_string):
            # some files and folders' names have spaces, so use the *filename to unpack
            permission, _no_idea, user, group, file_size, month_abbr, day, year_or_time, *file_name = file_or_folder_info_string.split()

            file_modified_date = self._get_datetime_from_ftp_list_date(year_or_time, month_abbr, day)
            file_path = "/".join([remote_folder_path, (" ".join(file_name) if isinstance(file_name, list) else file_name)])
            is_folder = permission.startswith("d")
            return data_info(file_path, file_modified_date, is_folder)

        files_and_folders = self.return_file_list(remote_folder_path)
        return [get_path_properties(file_or_folder_info) for file_or_folder_info in files_and_folders]

    def remove_file(self, remote_path, filename):
        """
        Returns the status of removing file which is present under 'remote_path'

        :param remote_path: FTP path
        :param filename: search file name
        :rtype: bool
        """
        if not self.is_file_present(remote_path, filename):
            self.logger.error("%s not found under %s", filename, remote_path)
            return False
        # calling again as is_file_present() already quit the FTP connection.
        self.cwd(remote_path)
        self.logger.info("setting type to binary")
        with self._ftp_connect(f"Failed to remove file {filename} from {remote_path}"):
            self.__ftp_session.sendcmd("TYPE i")
            self.__ftp_session.delete(filename)
        self.cwd(self._root_dir)
        return True

    def is_path_a_directory(self, ftp_path):
        """
        determines if an item listed on the ftp server is a valid directory or not uses mlsd command to do that

        :param ftp_path: string indicating a path to check
        :return: True if the path is a directory on the server else False
        :rtype: bool
        """
        if ftp_path == "/":  # Root directory always exist
            return True

        self._connect()
        try:
            if not ftp_path.startswith("/"):
                self.logger.warning(
                    f"Check for directory {ftp_path} which is not an absolute path. Checking it as relative to current working directory."
                )
            self.__ftp_session.cwd(ftp_path)
        except ftplib.error_perm as e:
            self.close_ftp_session()
            if "550 Failed to change directory" in str(e) or "Not a directory" in str(e) or "No such file or directory" in str(e):
                self.logger.info(f"Failed to change to {ftp_path=}. It's not a directory")
                return False
            raise
        self.cwd(self._root_dir)
        return True

    def _download_ftp_dir(self, ftp_root_path, local_path, overwrite, pattern):
        """
        replicates a directory on an ftp server recursively
        """
        self._create_local_dir(local_path)
        for file_name, file_info in self.__ftp_session.mlsd(ftp_root_path):
            full_file_path = os.path.join(local_path, file_name)
            ftp_file_path = f"{ftp_root_path}/{file_name}"

            if file_info["type"] == "dir":
                self._download_ftp_dir(ftp_file_path, full_file_path, overwrite, pattern)
            else:
                if not self._file_name_match_patern(pattern, file_name):
                    continue

                if os.path.exists(full_file_path) and not overwrite:
                    continue

                file_retr = f"RETR {ftp_file_path}"
                self._retrieve_binary_to_local_file(file_name, file_retr, full_file_path)

    def _file_name_match_patern(self, pattern, file_path):
        """
        returns True if filename matches the pattern
        """
        return True if pattern is None else bool(re.match(pattern, file_path))

    @staticmethod
    def _create_local_dir(file_path):
        if not os.path.exists(file_path):
            os.makedirs(file_path)

    def _remove_dir_tree_recursively(self, remote_path):
        try:
            dir_contents = self.return_dir_contents_as_dict(remote_path)
        except EmbeddedFrameworkException as e:
            if e.__cause__ and str(e.__cause__).startswith("550"):
                return  # No such file or directory — nothing to delete
            raise
        self._connect()
        for name, props in dir_contents.items():
            full_path = f"{remote_path}/{name}"
            if props.get("type") == "dir":
                self._remove_dir_tree_recursively(full_path)
            else:
                self.__ftp_session.delete(full_path)
        self.__ftp_session.rmd(remote_path)

    def remove_dir_tree_recursively(self, remote_path):
        """
        Returns the status of removing the directory as defined by 'remote_path'

        :param remote_path: FTP path
        """
        self._connect()
        self.logger.info("Recursively removing directory %s", remote_path)

        self._remove_dir_tree_recursively(remote_path)

        self.cwd(self._root_dir)

    def are_these_files_the_same(self, filepath1, filepath2):
        """
        compares two filepaths on the ftp server

        :rtype: bool
        """
        self._connect()
        dirpath1, file1 = self._split_into_filename_and_path(filepath1)
        dirpath2, file2 = self._split_into_filename_and_path(filepath2)
        return self.get_file_size(dirpath1, file1) == self.get_file_size(dirpath2, file2)

    @classmethod
    def _split_into_filename_and_path(cls, path):
        file1 = path.split("/")[-1]
        dirpath1 = path.replace(file1, "")
        return dirpath1, file1

    def rename(self, cur_name, new_name):
        """
        Checks if 'directory' exist and rename it to new_name.

        :param cur_name: current name
        :param new_name: new name
        :return: True if successful else False
        :rtype: bool
        """
        if not self.is_path_a_directory(cur_name):
            return False

        with self._ftp_connect(f"Failed to rename directory {cur_name} to {new_name}"):
            self.__ftp_session.rename(cur_name, new_name)

        self.cwd(self._root_dir)
        self.logger.info("Directory renamed from %s to: %s", cur_name, new_name)
        return self.is_path_a_directory(new_name)

    def copy_file_to_another_location(self, source, destination, filename):
        """
        Copy a file to another folder by downloading and uploading to FTP.

        This method downloads the file from the source location and uploads it to the destination.
        If the server supports ``SITE CPFR`` and ``SITE CPTO`` commands, an alternative approach
        would be to use those commands directly:

        Example::

            self.__ftp_session.sendcmd(f"SITE CPFR {source}/{filename}")
            self.__ftp_session.sendcmd(f"SITE CPTO {destination}")



        :param source: source file
        :param destination: destination path
        :param filename: file name
        """
        self.logger.debug("copying file %s from %s to %s", filename, source, destination)
        self.download(source, filename)
        self.upload(os.path.join(os.getcwd(), filename), destination)

    def is_uploading(self, file_path, check_interval=1, num_retries=3):
        """
        Determine if a file / folder is still being uploaded by checking its size multiple times.

        :param file_path: The path of the file / folder on the FTP server to check.
        :param check_interval: The time interval in seconds between size checks. Defaults to 1 second.
        :param num_retries: The number of times to check the file size. Defaults to 3.

        :rtype bool: True if the file is still being uploaded, False otherwise.
        """
        if Path(file_path).suffix == ".partial":
            self.logger.info(f"File {file_path} is still being uploaded (detected .partial extension).")
            return True

        args = (
            (file_path,) if self.is_path_a_directory(file_path) else (str(PurePosixPath(file_path).parent), PurePosixPath(file_path).name)
        )
        size = self.get_file_size(*args)

        for _ in range(num_retries):
            time.sleep(check_interval)
            new_size = self.get_file_size(*args)
            if size != new_size:
                return True
            size = new_size
        return False


class DirData(dict):
    def sort(self, sort_on=None, desc=False):
        """
        Sort the dictionary in place based on the specified key or filename if no keys is provided.

        Example with simplified data::

            d = DirData(
                {
                    "file1": {"m": "5", "s": 3},
                    "file3": {"m": "6", "s": 1},
                    "file2": {"m": "4", "s": 2},
                }
            )
            d.sort()
            # d == {"file1": {"m": "5", "s": 3}, "file2": {"m": "4", "s": 2}, "file3": {"m": "6", "s": 1}}
            d.sort(sort_on="m", desc=True)
            # d == {"file3": {"m": "6", "s": 1}, "file1": {"m": "5", "s": 3}, "file2": {"m": "4", "s": 2}}
            d.sort(sort_on="s", desc=False)
            # d == {"file3": {"m": "6", "s": 1}, "file2": {"m": "4", "s": 2}, "file1": {"m": "5", "s": 3}}

        :param sort_on: The key to sort the dictionary by. Sort by filename if not specified.
        :type sort_on: str | None
        :param order: The order to sort the dictionary by. Defaults to descending order. "desc" or "asc"
        :type order: bool
        """
        if sort_on:
            sorted_items = sorted(self.items(), key=lambda item: item[1].get(sort_on), reverse=desc)
        else:
            sorted_items = sorted(self.items(), reverse=desc)
        self.clear()
        self.update(sorted_items)


def make_ftp_engine(  # noqa: PLR0913 - explicit protocol connection settings
    hostname: str, username: str, password: str, *, port: int = 21, protocol: str = "ftp", timeout: float = 60
) -> FtpEngine:
    """Connect to FTP/FTPS with explicit credentials and server port."""
    if protocol not in ("ftp", "ftps"):
        message = "protocol must be ftp or ftps"
        raise ValueError(message)
    session = ftplib.FTP_TLS(context=ssl.create_default_context()) if protocol == "ftps" else ftplib.FTP()
    try:
        session.connect(hostname, port, timeout=timeout)
        session.login(username, password)
        if protocol == "ftps":
            session.prot_p()
        return FtpEngine(session, hostname, username, password, port, protocol)
    except Exception:
        session.close()
        raise
