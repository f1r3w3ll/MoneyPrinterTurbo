"""Persistent local productions and drafts, with background queue ownership."""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata
from pathlib import Path
from uuid import UUID, uuid4

from app.config import config
from app.controllers.manager.memory_manager import InMemoryTaskManager
from app.models import const
from app.models.schema import LongFormVideoParams
from app.services import state as sm
from app.services.checkpoint import CheckpointManager
from app.services.script_parser import ScriptParser
from app.services.studio_settings import validate_settings, redact
from app.services.studio_storage import write_json as _write
from app.services import studio_lease

ROOT = Path(config.root_dir) / 'storage' / 'studio'
_lock = threading.RLock()
_active = set()
_leases = {}
_manager = InMemoryTaskManager(max_concurrent_tasks=1, max_queued_tasks=20)
_READABLE_IDENTIFIER = re.compile(r'^[a-z0-9][a-z0-9-]{0,95}$')


def production_identifier(title):
    """Create a readable, collision-resistant folder name for a production."""
    normalized = unicodedata.normalize('NFKD', str(title or '')).encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^a-z0-9]+', '-', normalized.lower()).strip('-')[:58].strip('-') or 'video'
    return f'{slug}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid4().hex[:8]}'


def _folder(identifier, kind='productions'):
    identifier = str(identifier)
    try:
        identifier = str(UUID(identifier))
    except ValueError:
        if not _READABLE_IDENTIFIER.fullmatch(identifier):
            raise ValueError('Identificador de produção inválido.')
    folder = ROOT / kind / identifier
    if not folder.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Diretório de produção inválido.')
    return folder


def _read(filename):
    with Path(filename).open(encoding='utf-8') as file:
        return json.load(file)


def save_draft(script, draft_id=None):
    # Drafts can be unfinished; strict validation happens at production submission.
    identifier = draft_id or str(uuid4())
    with _lock:
        record = dict(id=identifier, script=script, updated_at=time.time())
        _write(_folder(identifier, 'drafts') / 'draft.json', record)
        return record


def list_drafts():
    with _lock:
        records = []
        for filename in (ROOT / 'drafts').glob('*/draft.json'):
            try:
                records.append(_read(filename))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda record: record['updated_at'], reverse=True)


def get_production(identifier):
    with _lock:
        record = _read(_folder(identifier) / 'production.json')
        manifest = _folder(identifier) / 'artifacts.json'
        if manifest.is_file():
            record['artifacts'] = _read(manifest)
        elif (_folder(identifier) / 'script.json').is_file():
            record.setdefault('artifacts', {})['script'] = str(_folder(identifier) / 'script.json')
        if (record['status'] in ('running', 'queued') and identifier not in _active
                and not studio_lease.is_locked(_folder(identifier) / 'worker.lock')):
            record.update(status='interrupted', error='O processo foi interrompido. Retome para continuar.')
        # Never expose a link to an artifact outside its own production directory.
        artifacts = record.get('artifacts', {})
        for key in ('video', 'thumbnail', 'script', 'subtitles'):
            value = artifacts.get(key)
            if value and (not Path(value).resolve().is_relative_to(_folder(identifier).resolve()) or not Path(value).is_file()):
                artifacts[key] = None
        if record['status'] == 'complete' and not all(artifacts.get(key) for key in ('video', 'thumbnail')):
            record.update(status='interrupted', error='Há arquivos finais ausentes. Retome para regenerá-los.')
        return record


def get_project(identifier):
    """Return a restorable project for new and legacy productions."""
    record = get_production(identifier)
    params = record.get('params', {})
    script = params.get('structured_script')
    artifact = (record.get('artifacts') or {}).get('script')
    if artifact and Path(artifact).is_file():
        try:
            script = json.loads(Path(artifact).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    if not script:
        raise ValueError('Esta produção não possui roteiro recuperável.')
    editorial = (script.get('metadata') or {}).get('editorial', {})
    return dict(id=record['id'], production=record, script=script,
                brief=editorial.get('brief', {}), packaging=editorial.get('selected_package', {}))


def list_productions():
    with _lock:
        records = []
        for filename in (ROOT / 'productions').glob('*/production.json'):
            try:
                records.append(get_production(filename.parent.name))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda record: record['created_at'], reverse=True)


def delete_production(identifier):
    """Permanently remove a finished or interrupted production and its files."""
    with _lock:
        record = get_production(identifier)
        if identifier in _active or record['status'] in ('queued', 'running'):
            raise ValueError('Não é possível excluir uma produção em andamento ou na fila.')
        folder = _folder(identifier)
        if not folder.is_dir():
            raise ValueError('Projeto de produção não encontrado.')
        _rmtree_production(folder)


def _rmtree_production(folder):
    try:
        shutil.rmtree(folder)
    except OSError:
        time.sleep(1)
        shutil.rmtree(folder, ignore_errors=True)


def published_archive_root():
    """Pasta onde produções publicadas são arquivadas (fora do repositório)."""
    return Path(config.root_dir).parent / 'PUBLICADOS'


def archive_production(identifier, archive_root=None):
    """Move os essenciais de uma produção publicada para a pasta PUBLICADOS e apaga o restante.

    Copia o vídeo final, a thumbnail, o roteiro e, quando existir, a descrição
    salva em publication.json; em seguida remove a pasta inteira da produção.
    """
    nl = chr(10)
    with _lock:
        record = get_production(identifier)
        if identifier in _active or record['status'] in ('queued', 'running'):
            raise ValueError('Não é possível arquivar uma produção em andamento ou na fila.')
        folder = _folder(identifier)
        if not folder.is_dir():
            raise ValueError('Projeto de produção não encontrado.')
        artifacts = record.get('artifacts') or {}
        video = artifacts.get('video')
        if not video or not Path(video).is_file():
            raise ValueError('O MP4 desta produção não está disponível para arquivar.')
        root = Path(archive_root) if archive_root else published_archive_root()
        dest = root / str(identifier)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(video), str(dest / 'video.mp4'))
        thumbnail = artifacts.get('thumbnail')
        if thumbnail and Path(thumbnail).is_file():
            shutil.move(str(thumbnail), str(dest / 'thumbnail.jpg'))
        script_file = folder / 'script.json'
        if script_file.is_file():
            shutil.move(str(script_file), str(dest / 'roteiro.json'))
        publication_file = folder / 'publication.json'
        if publication_file.is_file():
            publication = _read(publication_file)
            lines = [str(publication.get('title') or '').strip(), '',
                     str(publication.get('description') or '').strip()]
            tags = [str(tag).strip() for tag in (publication.get('tags') or []) if str(tag).strip()]
            if tags:
                lines += ['', 'Tags: ' + ', '.join(tags)]
            (dest / 'descricao-youtube.txt').write_text(nl.join(lines).strip() + nl, encoding='utf-8')
        _rmtree_production(folder)
        return str(dest)


def _public_params(params):
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not any(word in key.lower() for word in ('api_key', 'password', 'token', 'secret'))}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(params.model_dump(mode='json'))


def _migrate_legacy_visual_source(record, folder):
    """Move pre-Pexels Studio records to stock footage without losing progress.

    Old records omitted ``visual_mode`` and were therefore created while the
    model defaulted to Stable Diffusion.  On resume they must not submit a new
    Replicate prediction.  Existing valid images remain usable; only missing
    scenes will obtain Pexels clips.
    """
    saved = record.get('params') or {}
    if 'visual_mode' in saved:
        return record

    params_data = dict(saved)
    params_data['visual_mode'] = 'stock'
    params_data['stock_provider'] = 'pexels'
    params = LongFormVideoParams.model_validate(params_data)
    record['params'] = _public_params(params)
    record['updated_at'] = time.time()

    manager = CheckpointManager(record['id'], str(folder))
    state = manager.load_checkpoint()
    if state is not None:
        data = state.generated_files
        data['fingerprint'] = hashlib.sha256(params.model_dump_json().encode()).hexdigest()
        # Composition must be redone if an incomplete legacy visual set later
        # receives Pexels clips.  Audio, captions and existing scene images are
        # deliberately preserved.
        for key in ('video', 'base_video', 'duration_seconds', 'subtitles', 'thumbnail'):
            data.pop(key, None)
        data['stock_sources'] = [source for source in data.get('stock_sources', [])
                                 if isinstance(source, dict)]
        scenes = data.get('scenes', {})
        state.completed_scenes = [int(index) for index, entry in scenes.items()
                                  if isinstance(entry, dict) and
                                  (Path(entry.get('image') or '').is_file() or
                                   Path(entry.get('stock_video') or '').is_file())]
        state.current_phase = 'images'
        manager.save_checkpoint(state)

    _write(Path(folder) / 'production.json', record)
    return record


def _freeze_cta_assets(params, folder):
    """Copy channel assets into a production so later profile edits cannot break it."""
    assets = Path(folder) / 'assets'
    updates = {}
    for field, filename in (('channel_logo_path', 'logo'), ('cta_asset_path', 'cta')):
        source = Path(getattr(params, field, '') or '')
        if not source.is_file():
            continue
        target = assets / f'{filename}{source.suffix.lower()}'
        assets.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        updates[field] = str(target)
    return params.model_copy(update=updates) if updates else params


def submit(params):
    if not params.structured_script:
        raise ValueError('Gere ou importe um roteiro antes de produzir.')
    ScriptParser().parse_json_script(params.structured_script.model_dump())
    errors = validate_settings(params)
    if errors:
        raise ValueError('\n'.join(errors))
    identifier = production_identifier(params.structured_script.title)
    with _lock:
        params = _freeze_cta_assets(params, _folder(identifier))
        now = time.time()
        record = dict(id=identifier, title=params.structured_script.title, status='queued', phase='queue',
            progress=0, error=None, params=_public_params(params), artifacts={}, created_at=now, updated_at=now)
        _write(_folder(identifier) / 'production.json', record)
        _write(_folder(identifier) / 'project.json', dict(script=params.structured_script.model_dump(),
            editorial=(params.structured_script.metadata or {}).get('editorial', {}), created_at=now))
        _enqueue(identifier)
    return identifier


def _release(identifier):
    handle = _leases.pop(identifier, None)
    if handle is not None:
        studio_lease.release(handle)
    _active.discard(identifier)


def _enqueue(identifier):
    if identifier in _active:
        raise ValueError('Esta produção já está em execução ou na fila.')
    _leases[identifier] = studio_lease.acquire(_folder(identifier) / 'worker.lock')
    _active.add(identifier)
    try:
        record = _read(_folder(identifier) / 'production.json')
        record.update(status='queued', error=None, updated_at=time.time())
        _write(_folder(identifier) / 'production.json', record)
        sm.state.update_task(identifier, progress=0)
        _manager.add_task(_run, identifier)
    except Exception as exc:
        _release(identifier)
        record = _read(_folder(identifier) / 'production.json')
        record.update(status='failed', error=redact(exc), updated_at=time.time())
        _write(_folder(identifier) / 'production.json', record)
        raise


def resume(identifier):
    with _lock:
        record = get_production(identifier)
        if identifier in _active:
            raise ValueError('Esta produção já está em execução ou na fila.')
        if record['status'] == 'complete':
            raise ValueError('Esta produção já foi concluída.')
        record = _migrate_legacy_visual_source(record, _folder(identifier))
        params = LongFormVideoParams.model_validate(record['params'])
        errors = validate_settings(params)
        if errors:
            raise ValueError('\n'.join(errors))
        _enqueue(identifier)
    return identifier


def _run(identifier):
    from app.services.longform_pipeline import run
    folder = _folder(identifier)
    with _lock:
        record = _read(folder / 'production.json')
        record = _migrate_legacy_visual_source(record, folder)
    def report(phase, progress):
        with _lock:
            now = time.time()
            record.setdefault('started_at', now)
            record.update(status='running', phase=phase, progress=progress, updated_at=now)
            _write(folder / 'production.json', record)
            sm.state.update_task(identifier, progress=progress, phase=phase)
    try:
        report('script', 1)
        result = run(identifier, LongFormVideoParams.model_validate(record['params']), folder, report=report)
        with _lock:
            record.update(status='complete', phase='complete', progress=100, artifacts=result, error=None, updated_at=time.time())
            _write(folder / 'production.json', record)
        sm.state.update_task(identifier, state=const.TASK_STATE_COMPLETE, progress=100,
                            videos=[result['video']], thumbnail=result['thumbnail'])
    except Exception as exc:
        with _lock:
            record.update(status='failed', error=redact(exc), updated_at=time.time())
            _write(folder / 'production.json', record)
        sm.state.update_task(identifier, state=const.TASK_STATE_FAILED, progress=record['progress'], error=redact(exc))
    finally:
        with _lock:
            _release(identifier)
