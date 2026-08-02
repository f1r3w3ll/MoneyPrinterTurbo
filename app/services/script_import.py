"""Import a narration script and its scene/image timeline from a .docx package.

Expected document shape (produced by the "roteiro-youtube" style package):

- A section whose heading contains the word "script" holding the narration,
  broken into scenes by marker lines such as ``[SCENE 01]   00:48``.
- A table whose header row contains a "Scene" and an "Image prompt" column,
  giving the image prompt (and optionally a summary) for each scene.

The parser is intentionally tolerant of minor wording/formatting differences
since these documents are hand-edited: it locates sections by keyword rather
than exact heading text, and merges data from the narration section and the
scene table by scene number.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import docx

SCENE_MARKER_RE = re.compile(
    r"^\[?\s*SCENE\s*0*(?P<num>\d+)\s*\]?\s*(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)?\s*$",
    re.IGNORECASE,
)
SCENE_LABEL_RE = re.compile(r"SCENE\s*0*(?P<num>\d+)", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?$")


class ScriptImportError(ValueError):
    """Raised when the .docx does not contain a recognizable script/scene package."""


@dataclass
class ParsedScene:
    scene_id: str  # normalized, e.g. "01"
    order: int  # 1-based order of appearance in the narration
    narration: str  # narration text belonging to this scene, used for alignment
    planned_start_seconds: Optional[float] = None  # author's estimated timestamp
    summary: str = ""
    image_prompt: str = ""


@dataclass
class ImportedScript:
    video_script: str
    scenes: List[ParsedScene] = field(default_factory=list)


def parse_timestamp(value: str) -> Optional[float]:
    """Parse "MM:SS" or "HH:MM:SS" into seconds. Returns None if unparsable."""
    if not value:
        return None
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        return None
    hours = int(match.group("h"))
    minutes = int(match.group("m"))
    seconds = int(match.group("s") or 0)
    # "MM:SS" is far more common than "HH:MM:SS" in these scripts, and an
    # "HH" value above 23 can only mean it was actually minutes.
    if match.group("s") is None:
        return hours * 60 + minutes
    return hours * 3600 + minutes * 60 + seconds


def _normalize_scene_num(text: str) -> Optional[str]:
    match = SCENE_LABEL_RE.search(text or "")
    if not match:
        return None
    return f"{int(match.group('num')):02d}"


def _find_script_section_paragraphs(document) -> List:
    """Return the paragraphs belonging to the narration/"full script" section."""
    heading_styles = {"heading 1", "heading 2", "heading 3"}
    paragraphs = document.paragraphs

    start_index = None
    for i, p in enumerate(paragraphs):
        style_name = (p.style.name if p.style else "").lower()
        if style_name in heading_styles and "script" in p.text.lower():
            start_index = i + 1
            break

    if start_index is None:
        raise ScriptImportError(
            "could not find a heading containing 'script' in the .docx; "
            "expected a section such as 'Full Script'"
        )

    end_index = len(paragraphs)
    for i in range(start_index, len(paragraphs)):
        style_name = (paragraphs[i].style.name if paragraphs[i].style else "").lower()
        if style_name in heading_styles:
            end_index = i
            break

    return paragraphs[start_index:end_index]


def _extract_scenes_from_script_section(paragraphs) -> List[ParsedScene]:
    scenes: List[ParsedScene] = []
    current: Optional[ParsedScene] = None
    order = 0

    for p in paragraphs:
        text = p.text.strip()
        if not text:
            continue

        marker = SCENE_MARKER_RE.match(text)
        if marker:
            order += 1
            current = ParsedScene(
                scene_id=f"{int(marker.group('num')):02d}",
                order=order,
                narration="",
                planned_start_seconds=parse_timestamp(marker.group("timestamp")),
            )
            scenes.append(current)
            continue

        if current is None:
            # Editorial notes before the first scene marker (e.g. "Narration
            # only. Scene markers are for the editor and are not read
            # aloud.") are not narration and are skipped.
            continue

        current.narration = f"{current.narration}\n{text}".strip()

    if not scenes:
        raise ScriptImportError(
            "no '[SCENE NN]' markers found in the script section; "
            "cannot split narration into timed scenes"
        )

    return scenes


def _find_scene_table(document) -> Optional[Dict[str, Dict[str, str]]]:
    """Return {scene_id: {"summary": ..., "image_prompt": ...}} from the scene table, if any."""
    for table in document.tables:
        if not table.rows:
            continue
        header_cells = [c.text.strip().lower() for c in table.rows[0].cells]
        if not any("scene" in h for h in header_cells) or not any(
            "image" in h for h in header_cells
        ):
            continue

        col_index = {}
        for idx, header in enumerate(header_cells):
            # Check the more specific headers first: "Scene summary" and
            # "Scene" both contain "scene", so "summary"/"image" must win.
            if "summary" in header:
                col_index["summary"] = idx
            elif "image" in header:
                col_index["image_prompt"] = idx
            elif "scene" in header:
                col_index.setdefault("scene", idx)

        by_scene: Dict[str, Dict[str, str]] = {}
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if "scene" not in col_index or col_index["scene"] >= len(cells):
                continue
            scene_id = _normalize_scene_num(cells[col_index["scene"]])
            if not scene_id:
                continue
            by_scene[scene_id] = {
                "summary": cells[col_index["summary"]]
                if "summary" in col_index and col_index["summary"] < len(cells)
                else "",
                "image_prompt": cells[col_index["image_prompt"]]
                if "image_prompt" in col_index and col_index["image_prompt"] < len(cells)
                else "",
            }
        return by_scene

    return None


def parse_docx_script(file_path: str) -> ImportedScript:
    """Parse a .docx script package into narration text plus a timed scene list."""
    document = docx.Document(file_path)

    script_paragraphs = _find_script_section_paragraphs(document)
    scenes = _extract_scenes_from_script_section(script_paragraphs)

    scene_table = _find_scene_table(document)
    if scene_table:
        for scene in scenes:
            extra = scene_table.get(scene.scene_id)
            if extra:
                scene.summary = extra["summary"]
                scene.image_prompt = extra["image_prompt"]

    video_script = "\n\n".join(scene.narration for scene in scenes if scene.narration)

    return ImportedScript(video_script=video_script, scenes=scenes)
