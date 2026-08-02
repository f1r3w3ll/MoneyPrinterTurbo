import os

from app.models.schema import ScriptScene
from app.services.alignment import align_scenes_to_subtitle


def _write_srt(path, entries):
    lines = []
    for idx, (start, end, text) in enumerate(entries, start=1):
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _scene(scene_id, order, narration):
    return ScriptScene(scene_id=scene_id, order=order, narration=narration)


def test_align_scenes_to_subtitle_matches_by_sentence_count(tmp_path):
    srt_path = os.path.join(tmp_path, "subtitle.srt")
    _write_srt(
        srt_path,
        [
            ("00:00:00,000", "00:00:02,500", "This is the first sentence."),
            ("00:00:02,500", "00:00:05,000", "It has two sentences."),
            ("00:00:05,000", "00:00:09,000", "This is the second scene narration."),
        ],
    )

    scenes = [
        _scene("01", 1, "This is the first sentence.\nIt has two sentences."),
        _scene("02", 2, "This is the second scene narration."),
    ]

    aligned = align_scenes_to_subtitle(scenes, srt_path)

    assert aligned[0].start_seconds == 0.0
    assert aligned[0].end_seconds == 5.0
    assert aligned[1].start_seconds == 5.0
    assert aligned[1].end_seconds == 9.0


def test_align_scenes_to_subtitle_leaves_unaligned_when_out_of_entries(tmp_path):
    srt_path = os.path.join(tmp_path, "subtitle.srt")
    _write_srt(
        srt_path,
        [
            ("00:00:00,000", "00:00:02,000", "Only one sentence here."),
        ],
    )

    scenes = [
        _scene("01", 1, "Only one sentence here."),
        _scene("02", 2, "A second scene with no matching subtitle entry."),
    ]

    aligned = align_scenes_to_subtitle(scenes, srt_path)

    assert aligned[0].start_seconds == 0.0
    assert aligned[0].end_seconds == 2.0
    assert aligned[1].start_seconds is None
    assert aligned[1].end_seconds is None


def test_align_scenes_to_subtitle_missing_file_leaves_scenes_unaligned(tmp_path):
    scenes = [_scene("01", 1, "Some narration.")]
    aligned = align_scenes_to_subtitle(scenes, os.path.join(tmp_path, "missing.srt"))
    assert aligned[0].start_seconds is None
