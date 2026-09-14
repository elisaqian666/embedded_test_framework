"""Local artifact utilities usable without a test runner."""
import hashlib
from pathlib import Path
import shutil


class ArtifactHelper:
    @staticmethod
    def sha256(path):
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def copy(source, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
