import os
from pathlib import Path
from core import DisguiseEngine, DisguiseError


def _write(path: Path, size: int = 512):
    path.write_bytes(os.urandom(size))


def test_empty_target_queue_reports_zero(tmp_path):
    engine = DisguiseEngine()
    engine.parse_and_set_magic("T1")
    success, failed = engine.handle_toggle(
        progress_cb=lambda *a: None,
        log_cb=lambda *a: None,
        process_events_cb=lambda: None,
    )
    assert success == 0
    assert failed == []


def test_missing_mask_library_raises(tmp_path):
    src = tmp_path / "a.txt"
    _write(src)
    engine = DisguiseEngine()
    engine.parse_and_set_magic("T1")
    engine.target_files = [str(src)]
    engine.mask_library = []
    try:
        engine.handle_toggle(lambda *a: None, lambda *a: None, lambda: None)
        raise AssertionError("expected DisguiseError")
    except DisguiseError:
        pass


def test_rename_mapping_skips_when_disabled(tmp_path):
    a = tmp_path / "a.txt"
    mask = tmp_path / "m.mp4"
    _write(a)
    _write(mask)

    engine = DisguiseEngine()
    engine.parse_and_set_magic("T2")
    engine.mask_library = [str(mask)]
    engine.target_files = [str(a)]
    engine.rename_mapping = False
    engine.mapping_output_path = str(tmp_path / "mapping.txt")
    engine.disguise_mapping_txt = False

    success, failed = engine.handle_toggle(lambda *a: None, lambda *a: None, lambda: None)
    assert success == 1
    assert not (tmp_path / "mapping.txt").exists()


def test_detect_status_counts_states(tmp_path):
    a = tmp_path / "a.txt"
    mask = tmp_path / "m.mp4"
    _write(a)
    _write(mask)

    engine = DisguiseEngine()
    engine.parse_and_set_magic("T3")
    engine.mask_library = [str(mask)]
    engine.target_files = [str(a)]

    original_count, disguised_count, failed = engine.detect_status(
        lambda *a: None, lambda *a: None, lambda: None
    )
    assert original_count == 1
    assert disguised_count == 0
    assert failed == []
