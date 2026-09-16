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
    valid_audio, valid_image, valid_stock_video, valid_video, make_thumbnail, write_subtitles, append_cta,
    cta_duration)
from app.services.studio_stock import fetch_scene_clip


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
    provider_fallbacks = data.setdefault('provider_fallbacks', [])

    def save(phase, progress):
        state.current_phase = phase
        state.timestamp = time.time()
        if params.enable_checkpointing:
            manager.save_checkpoint(state)
        write_json(folder / 'artifacts.json', dict(video=data.get('video'), thumbnail=data.get('thumbnail'),
            script=str(folder / 'script.json'), subtitles=data.get('subtitles'),
            stock_sources=data.get('stock_sources', []),
            provider_fallbacks=data.get('provider_fallbacks', []),
            duration_seconds=data.get('duration_seconds', sum(entry.get('duration', 0.) for entry in entries.values()))))
        report(phase, progress)

    try:
        script_file = folder / 'script.json'
        script_file.write_text(script.model_dump_json(indent=2), encoding='utf-8')
        save('script', 5)
        if stop_at == 'script':
            return {'script': str(script_file)}
        for number, scene in enumerate(script.scenes):
            entry = entries.setdefault(str(scene.index), {'index': scene.index})
            if entry.get('transition', 'none') != scene.transition:
                data.pop('video', None)
                data.pop('base_video', None)
            entry['transition'] = scene.transition
            if not valid_audio(entry.get('audio')):
                data.pop('video', None)
                data.pop('base_video', None)
                data.pop('duration_seconds', None)
                data.pop('subtitles', None)
                save('audio', 5 + int(30 * number / len(script.scenes)))
                audio = generate_scene_audio(scene, params, folder / f'audio-{scene.index}.mp3')
                entry.update(audio=audio['path'], duration=audio['duration'], cues=audio['cues'])
                save('audio', 5 + int(30 * (number + 1) / len(script.scenes)))
        if stop_at == 'audio':
            return {'audio_chunks': [entry['audio'] for entry in entries.values()]}
        visual_mode = getattr(params, 'visual_mode', 'ai')
        stock_sources = data.setdefault('stock_sources', [])
        for number, scene in enumerate(script.scenes):
            entry = entries[str(scene.index)]
            use_stock = visual_mode == 'stock' or (visual_mode == 'hybrid' and scene.index % 3 != 2)
            if use_stock and not valid_stock_video(entry.get('stock_video')):
                data.pop('video', None)
                data.pop('base_video', None)
                save('images', 35 + int(20 * number / len(script.scenes)))
                stock = fetch_scene_clip(scene, params, folder / 'stock')
                entry['stock_video'] = stock['path']
                entry['stock_source'] = {key: value for key, value in stock.items() if key != 'path'}
                stock_sources = [item for item in stock_sources if item.get('scene_index') != scene.index]
                stock_sources.append(dict(scene_index=scene.index, **entry['stock_source']))
                data['stock_sources'] = stock_sources
                state.completed_scenes = [int(key) for key, item in entries.items()
                                          if item.get('image') or item.get('stock_video')]
                save('images', 35 + int(20 * (number + 1) / len(script.scenes)))
            elif not use_stock and not valid_image(entry.get('image')):
                data.pop('video', None)
                data.pop('base_video', None)
                save('images', 35 + int(20 * number / len(script.scenes)))
                try:
                    generated = generate_scene_image(scene, params, folder / f'scene-{scene.index}.png')
                except RuntimeError as exc:
                    if not str(exc).startswith('As fontes de imagem estão sem créditos:'):
                        raise
                    stock = fetch_scene_clip(scene, params, folder / 'stock')
                    entry['stock_video'] = stock['path']
                    entry['stock_source'] = {key: value for key, value in stock.items() if key != 'path'}
                    stock_sources = [item for item in stock_sources if item.get('scene_index') != scene.index]
                    stock_sources.append(dict(scene_index=scene.index, **entry['stock_source']))
                    data['stock_sources'] = stock_sources
                    event = dict(phase='images', scene_index=scene.index,
                                 unavailable=str(exc).removeprefix('As fontes de imagem estão sem créditos:').strip(),
                                 replacement=f"stock:{stock.get('provider', params.stock_provider)}")
                    if event not in provider_fallbacks:
                        provider_fallbacks.append(event)
                    state.completed_scenes = [int(key) for key, item in entries.items()
                                              if item.get('image') or item.get('stock_video')]
                    save('images', 35 + int(20 * (number + 1) / len(script.scenes)))
                    continue
                if isinstance(generated, dict):
                    entry['image'] = generated['path']
                    for unavailable in generated.get('unavailable_providers', []):
                        event = dict(phase='images', scene_index=scene.index, unavailable=unavailable,
                                     replacement=generated.get('provider'))
                        if event not in provider_fallbacks:
                            provider_fallbacks.append(event)
                else:  # Compatibility with integrations that still return a file path.
                    entry['image'] = generated
                state.completed_scenes = [int(key) for key, item in entries.items()
                                          if item.get('image') or item.get('stock_video')]
                save('images', 35 + int(20 * (number + 1) / len(script.scenes)))
        if stop_at == 'images':
            return {'images': {key: entry.get('image') for key, entry in entries.items() if entry.get('image')},
                    'stock_sources': stock_sources,
                    'stock_videos': {key: entry.get('stock_video') for key, entry in entries.items() if entry.get('stock_video')}}
        ordered = [entries[str(scene.index)] for scene in script.scenes]
        save('subtitles', 56)
        subtitles = write_subtitles(ordered, folder / 'subtitles.srt') if params.subtitle_enabled else None
        data['subtitles'] = subtitles
        if stop_at in ('subtitle', 'subtitles'):
            return {'subtitles': subtitles}
        expected = sum(entry['duration'] for entry in ordered)
        final_expected = expected + cta_duration(params)
        if not valid_video(data.get('video'), expected_duration=final_expected):
            data.pop('video', None)
            save('composition', 60)
            if not valid_video(data.get('base_video'), expected_duration=expected):
                data['base_video'] = compose(ordered, params, folder,
                    progress=lambda fraction: report('composition', 60 + int(fraction * 30)),
                    output_name=f'{folder.name}.mp4')
            save('composition', 90)
            data['video'] = append_cta(data['base_video'], params, folder)
            if not valid_video(data['video'], expected_duration=final_expected):
                data.pop('video', None)
                raise RuntimeError('A duração do vídeo com CTA não corresponde à duração esperada.')
        data['duration_seconds'] = final_expected
        save('thumbnail', 92)
        if stop_at != 'video' and not valid_image(data.get('thumbnail')):
            first_stock_video = next((entry.get('stock_video') for entry in ordered if entry.get('stock_video')), None)
            if first_stock_video:
                data['thumbnail'] = make_thumbnail(script, params, folder, stock_video=first_stock_video)
            else:
                data['thumbnail'] = make_thumbnail(script, params, folder)
        result = dict(video=data['video'], thumbnail=data.get('thumbnail'), script=str(script_file),
                      subtitles=subtitles, duration_seconds=data['duration_seconds'], stock_sources=stock_sources)
        save('complete', 100)
        # Retain validated artifacts for recovery if a final file is lost later.
        return result
    except Exception:
        state.error_count += 1
        if params.enable_checkpointing:
            manager.save_checkpoint(state)
        raise
