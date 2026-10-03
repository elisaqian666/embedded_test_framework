from embedded_test_framework.helpers.he_file import FileHelper


def test_file_helper_compares_identical_files(tmp_path) -> None:
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")

    assert FileHelper.are_files_identical(first, second)
