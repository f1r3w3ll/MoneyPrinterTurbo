import os

from app.models.schema import ScriptScene
from app.services.alignment import align_scenes_to_subtitle, finalize_scene_timeline


def _write_srt(path, entries):
    lines = []
    for idx, (start, end, text) in enumerate(entries, start=1):
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _scene(scene_id, order, narration, planned_start_seconds=None):
    return ScriptScene(
        scene_id=scene_id,
        order=order,
        narration=narration,
        planned_start_seconds=planned_start_seconds,
    )


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


def test_finalize_scene_timeline_uses_real_alignment_when_available():
    scenes = [
        _scene("01", 1, "first", planned_start_seconds=0),
        _scene("02", 2, "second", planned_start_seconds=50),
        _scene("03", 3, "third", planned_start_seconds=100),
    ]
    scenes[0].start_seconds = 0.0
    scenes[1].start_seconds = 60.0  # real TTS ran slower than the planned pace
    # scenes[2] failed to align (start_seconds stays None)

    result = finalize_scene_timeline(scenes, audio_duration=130.0)

    assert result[0].start_seconds == 0.0
    assert result[0].end_seconds == 60.0
    assert result[1].start_seconds == 60.0
    # scene 3 falls back to proportional scaling of its planned timestamp:
    # scale = 130 / 100 = 1.3 -> 100 * 1.3 = 130, clamped to audio_duration.
    assert result[2].start_seconds == 130.0
    assert result[2].end_seconds == 130.0


def test_finalize_scene_timeline_is_monotonic_even_with_noisy_alignment():
    scenes = [
        _scene("01", 1, "first", planned_start_seconds=0),
        _scene("02", 2, "second", planned_start_seconds=10),
        _scene("03", 3, "third", planned_start_seconds=20),
    ]
    # Simulate a bad alignment that would otherwise go backwards in time.
    scenes[0].start_seconds = 5.0
    scenes[1].start_seconds = 2.0
    scenes[2].start_seconds = None

    result = finalize_scene_timeline(scenes, audio_duration=20.0)

    starts = [s.start_seconds for s in result]
    assert starts == sorted(starts)
    for i in range(len(result) - 1):
        assert result[i].end_seconds == result[i + 1].start_seconds
    assert result[-1].end_seconds == 20.0


def test_finalize_scene_timeline_falls_back_to_even_spacing_without_planned_timestamps():
    scenes = [
        _scene("01", 1, "first"),
        _scene("02", 2, "second"),
        _scene("03", 3, "third"),
        _scene("04", 4, "fourth"),
    ]

    result = finalize_scene_timeline(scenes, audio_duration=40.0)

    assert [s.start_seconds for s in result] == [0.0, 10.0, 20.0, 30.0]
    assert result[-1].end_seconds == 40.0


def test_finalize_scene_timeline_empty_list_returns_empty():
    assert finalize_scene_timeline([], audio_duration=10.0) == []
