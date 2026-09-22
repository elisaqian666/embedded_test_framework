import logging

from embedded_framework.basic_test_setup import BasicTestClass
import embedded_framework.lib.logging_extras as logging_extras


def test_setup_creates_one_timestamped_log_folder(tmp_path, monkeypatch):
    original = logging_extras._TEST_LOG_FOLDER
    monkeypatch.chdir(tmp_path)
    logging_extras._TEST_LOG_FOLDER = None
    try:
        BasicTestClass._initialize_log_folder()
        folder = logging_extras._TEST_LOG_FOLDER
        assert folder is not None and folder.parent == tmp_path / "test_logs"
        assert (folder / "test.log").is_file()
    finally:
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename.startswith(str(tmp_path)):
                logging.getLogger().removeHandler(handler)
                handler.close()
        logging_extras._TEST_LOG_FOLDER = original
