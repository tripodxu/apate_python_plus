import os
from pathlib import Path
from core import DisguiseEngine, is_disguised_file


def _write_binary(path: Path, size: int = 1024):
    path.write_bytes(os.urandom(size))


def test_rename_sequence_and_mapping_txt_created(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    mask = tmp_path / "mask.mp4"
    _write_binary(a)
    _write_binary(b)
    _write_binary(mask, 2048)

    mapping_path = tmp_path / "mapping.txt"

    engine = DisguiseEngine()
    engine.parse_and_set_magic("TEST")
    engine.mask_library = [str(mask)]

    engine.target_files = [str(a), str(b)]
    engine.rename_mapping = True
    engine.mapping_output_path = str(mapping_path)
    engine.disguise_mapping_txt = False

    success, failed = engine.handle_toggle(
        progress_cb=lambda *a: None,
        log_cb=lambda *a: None,
        process_events_cb=lambda: None,
    )

    assert success == 2, failed
    assert len(engine.target_files) == 2
    out_names = [Path(p).name for p in engine.target_files]
    assert out_names == ["1.mp4", "2.mp4"]

    assert mapping_path.exists(), "mapping txt should be created"
    content = mapping_path.read_text(encoding="utf-8")
    assert "a.mp4 -> 1.mp4" in content
    assert "b.mp4 -> 2.mp4" in content


def test_mapping_txt_can_be_disguised(tmp_path):
    a = tmp_path / "a.mp4"
    mask = tmp_path / "mask.mp4"
    _write_binary(a)
    _write_binary(mask, 2048)

    mapping_path = tmp_path / "mapping.txt"

    engine = DisguiseEngine()
    engine.parse_and_set_magic("TEST")
    engine.mask_library = [str(mask)]

    engine.target_files = [str(a)]
    engine.rename_mapping = True
    engine.mapping_output_path = str(mapping_path)
    engine.disguise_mapping_txt = True

    success, failed = engine.handle_toggle(
        progress_cb=lambda *a: None,
        log_cb=lambda *a: None,
        process_events_cb=lambda: None,
    )

    assert success == 1, failed
    assert is_disguised_file(engine.mapping_output_path, b"TEST")
