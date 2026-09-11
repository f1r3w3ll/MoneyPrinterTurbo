"""Resumable complete long-form production, independent of Streamlit."""
import hashlib
import json
import time
from pathlib import Path

from app.models.schema import CheckpointState
from app.services.checkpoint import CheckpointManager
from app.services.script_parser import ScriptParser
from app.services.studio_storage import write_json
from app.services.longform_media import (generate_scene_audio, generate_scene_image, compose,
    valid_audio, valid_image, valid_video, make_thumbnail, write_subtitles, append_cta)


def run(task_id, params, folder, report=None, stop_at='complete'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = report or (lambda phase, progress: None)
    script = ScriptParser().parse_json_script(params.structured_script.model_dump())
    manager = CheckpointManager(task_id, str(folder))
    fingerprint = hashlib.sha256(params.model_dump_json().encode()).hexdigest()
    state = manager.load_checkpoint() if params.enable_checkpointing else None
    if params.enable_checkpointing and manager.checkpoint_exists() and state is None:
        raise ValueError('Checkpoint ilegível. Preserve os arquivos e inicie uma nova produção.')
    if state and state.generated_files.get('fingerprint') != fingerprint:
        raise ValueError('Os parâmetros diferem do checkpoint. Crie uma nova produção para aplicar alterações.')
    if state is None:
        state = CheckpointState(task_id=task_id, current_phase='script', completed_scenes=[],
            generated_files={'fingerprint': fingerprint, 'scenes': {}}, timestamp=time.time())
    data = state.generated_files
    entries = data['scenes']

    def save(phase, progress):
        state.current_phase = phase
        state.timestamp = time.time()
        if params.enable_checkpointing:
            manager.save_checkpoint(state)
        write_json(folder / 'artifacts.json', dict(video=data.get('video'), thumbnail=data.get('thumbnail'),
            script=str(folder / 'script.json'), subtitles=data.get('subtitles'),
            duration_seconds=sum(entry.get('duration', 0.) for entry in entries.values())))
        report(phase, progress)

    try:
        script_file = folder / 'script.json'
        script_file.write_text(script.model_dump_json(indent=2), encoding='utf-8')
        save('script', 5)
        if stop_at == 'script':
            return {'script': str(script_file)}
        for number, scene in enumerate(script.scenes):
            entry = entries.setdefault(str(scene.index), {'index': scene.index})
            if not valid_audio(entry.get('audio')):
                data.pop('video', None)
                data.pop('subtitles', None)
                save('audio', 5 + int(30 * number / len(script.scenes)))
                audio = generate_scene_audio(scene, params, folder / f'audio-{scene.index}.mp3')
                entry.update(audio=audio['path'], duration=audio['duration'], cues=audio['cues'])
                save('audio', 5 + int(30 * (number + 1) / len(script.scenes)))
        if stop_at == 'audio':
            return {'audio_chunks': [entry['audio'] for entry in entries.values()]}
        for number, scene in enumerate(script.scenes):
            entry = entries[str(scene.index)]
            if not valid_image(entry.get('image')):
                data.pop('video', None)
                save('images', 35 + int(20 * number / len(script.scenes)))
                entry['image'] = generate_scene_image(scene, params, folder / f'scene-{scene.index}.png')
                state.completed_scenes = [int(key) for key, item in entries.items() if item.get('image')]
                save('images', 35 + int(20 * (number + 1) / len(script.scenes)))
        if stop_at == 'images':
            return {'images': {key: entry['image'] for key, entry in entries.items()}}
        ordered = [entries[str(scene.index)] for scene in script.scenes]
        save('subtitles', 56)
        subtitles = write_subtitles(ordered, folder / 'subtitles.srt') if params.subtitle_enabled else None
        data['subtitles'] = subtitles
        if stop_at in ('subtitle', 'subtitles'):
            return {'subtitles': subtitles}
        expected = sum(entry['duration'] for entry in ordered)
        if not valid_video(data.get('video'), expected_duration=expected):
            data.pop('video', None)
            save('composition', 60)
            data['video'] = compose(ordered, params, folder,
                progress=lambda fraction: report('composition', 60 + int(fraction * 30)),
                output_name=f'{folder.name}.mp4')
            data['video'] = append_cta(data['video'], params, folder)
        save('thumbnail', 92)
        if stop_at != 'video' and not valid_image(data.get('thumbnail')):
            data['thumbnail'] = make_thumbnail(script, params, folder)
        result = dict(video=data['video'], thumbnail=data.get('thumbnail'), script=str(script_file),
                      subtitles=subtitles, duration_seconds=sum(entry['duration'] for entry in ordered))
        save('complete', 100)
        # Retain validated artifacts for recovery if a final file is lost later.
        return result
    except Exception:
        state.error_count += 1
        if params.enable_checkpointing:
            manager.save_checkpoint(state)
        raise
