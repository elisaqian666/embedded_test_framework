import logging
from pathlib import Path

from embedded_framework.basic_test_setup import BasicTestClass
import embedded_framework.lib.logging_extras as logging_extras


def test_setup_creates_one_timestamped_log_folder(tmp_path, monkeypatch):
    original = logging_extras._TEST_LOG_FOLDER
    monkeypatch.chdir(tmp_path)
    logging_extras._TEST_LOG_FOLDER = None
    try:
        BasicTestClass._initialize_log_folder()
        folder = logging_extras._TEST_LOG_FOLDER
        assert folder is not None and folder.parent == Path(__file__).resolve().parents[2] / "test_logs"
        assert (folder / "test.log").is_file()
        assert (folder / "test-results.txt").is_file()
    finally:
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler, logging.FileHandler) and folder and handler.baseFilename.startswith(str(folder)):
                logging.getLogger().removeHandler(handler)
                handler.close()
        logging_extras._TEST_LOG_FOLDER = original


def test_setup_creates_method_folders_with_one_class_summary(tmp_path):
    class SampleTestCase(BasicTestClass):
        pass

    SampleTestCase.base_log_store_folder = str(tmp_path)
    SampleTestCase._initialize_log_folder()
    first, second = SampleTestCase(), SampleTestCase()
    first._test_id = "test_example.py::SampleTestCase::test_first"
    second._test_id = "test_example.py::SampleTestCase::test_second"

    first.setUp()
    second.setUp()

    assert Path(first.test_method_log_store_folder).parent == Path(SampleTestCase.test_class_log_store_folder)
    assert first.test_method_log_store_folder != second.test_method_log_store_folder
    assert first.test_summary_file == second.test_summary_file
    assert Path(first.test_summary_file).is_file()
