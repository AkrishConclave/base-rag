"""Проверки безопасного выбора исходного файла для индексации."""

import os

import pytest

from api.chroma import ingest as ingest_module


def _use_temporary_project_root(monkeypatch, tmp_path):
    """Направляет поиск файлов только в изолированный временный проект."""
    fake_module = tmp_path / "api" / "chroma" / "ingest.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()
    monkeypatch.setattr(ingest_module, "__file__", str(fake_module))
    monkeypatch.setattr(ingest_module.settings, "support_dir", "")
    monkeypatch.chdir(tmp_path)


def test_find_support_json_rejects_example_only(monkeypatch, tmp_path):
    """Шаблон без реального экспорта не должен запускать индексацию."""
    _use_temporary_project_root(monkeypatch, tmp_path)
    (tmp_path / "support_example.json").write_text('{"support": []}', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="является только шаблоном"):
        ingest_module.find_support_json()


def test_find_support_json_selects_newest_timestamp_and_keeps_older_files(monkeypatch, tmp_path):
    """Timestamp в имени важнее mtime, старые экспорты и шаблон сохраняются."""
    _use_temporary_project_root(monkeypatch, tmp_path)
    example_file = tmp_path / "support_example.json"
    older_file = tmp_path / "support_202610311200.json"
    newer_file = tmp_path / "support_202611011000.json"
    example_file.write_text('{"support": []}', encoding="utf-8")
    older_file.write_text('{"support": [{"id": 1}]}', encoding="utf-8")
    newer_file.write_text('{"support": [{"id": 2}]}', encoding="utf-8")
    os.utime(older_file, (200, 200))
    os.utime(newer_file, (100, 100))

    selected_file = ingest_module.find_support_json()

    assert os.path.samefile(selected_file, newer_file)
    assert example_file.exists()
    assert older_file.exists()
    assert newer_file.exists()
