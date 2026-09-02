import os
from pathlib import Path
from apluse.core import DisguiseEngine, DisguiseError, is_disguised_file


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


def test_handle_toggle_disguise_then_reveal_roundtrip(tmp_path):
    """连续两次 handle_toggle：第一次伪装、第二次应还原回原始文件名与内容。"""
    a = tmp_path / "a.txt"
    a.write_text("roundtrip-content", encoding="utf-8")
    mask = tmp_path / "m.mp4"
    _write(mask)

    engine = DisguiseEngine()
    engine.parse_and_set_magic("RT")
    engine.mask_library = [str(mask)]
    engine.target_files = [str(a)]

    noop = lambda *args: None
    success, failed = engine.handle_toggle(noop, noop, lambda: None)
    assert success == 1 and failed == []
    disguised = Path(engine.target_files[0])
    assert is_disguised_file(str(disguised), b"RT")

    success, failed = engine.handle_toggle(noop, noop, lambda: None)
    assert success == 1 and failed == []
    restored = Path(engine.target_files[0])
    assert restored.name == "a.txt"
    assert restored.read_text(encoding="utf-8") == "roundtrip-content"
