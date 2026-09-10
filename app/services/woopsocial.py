"""WoopSocial publishing client. Credentials stay in local configuration."""
from pathlib import Path
import time
import requests

from app.config import config

BASE_URL = 'https://api.woopsocial.com/v1'
# A session upload bypasses the API origin for the file bytes. It is more
# resilient for the long-form MP4s produced by the Studio.
CHUNKED_UPLOAD_THRESHOLD_BYTES = 25 * 1024 * 1024


def _headers():
    key = config.app.get('woopsocial_api_key', '')
    if not key:
        raise ValueError('Configure a chave WoopSocial em Configurações.')
    return {'Authorization': f'Bearer {key}'}


def _ensure_success(response, action):
    """Keep the API's actionable error detail instead of a generic HTTP error."""
    try:
        response.raise_for_status()
    except Exception as exc:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get('error_message') or payload.get('message') or payload.get('error')
        else:
            detail = None
        detail = detail or getattr(response, 'text', '') or str(exc)
        raise ValueError(f'WoopSocial recusou {action}: {detail}') from exc


def youtube_accounts():
    response = requests.get(f'{BASE_URL}/social-accounts', headers=_headers(), timeout=30)
    _ensure_success(response, 'a lista de canais')
    payload = response.json()
    values = payload.get('data', payload) if isinstance(payload, dict) else payload
    if isinstance(values, dict):
        values = values.get('items') or values.get('socialAccounts') or []
    if not isinstance(values, list):
        raise ValueError('A WoopSocial retornou uma lista de canais em formato inválido.')
    return [item for item in values if isinstance(item, dict) and str(item.get('platform', '')).upper() == 'YOUTUBE']


def projects():
    response = requests.get(f'{BASE_URL}/projects', headers=_headers(), timeout=30)
    _ensure_success(response, 'a lista de projetos')
    payload = response.json()
    values = payload.get('data', payload) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError('A WoopSocial retornou projetos em formato inválido.')
    return [item for item in values if isinstance(item, dict) and item.get('id')]


def account_label(account):
    """Return the human channel name supplied by WoopSocial when available."""
    for key in ('name', 'displayName', 'accountName', 'username', 'userName', 'handle'):
        value = account.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(account.get('id', 'Canal sem nome'))


def _media_id(payload):
    """Read the media identifier across the API's current and legacy shapes."""
    if not isinstance(payload, dict):
        return None
    return (payload.get('mediaId') or payload.get('id') or (payload.get('data') or {}).get('id')
            or (payload.get('media') or {}).get('id'))


def _report_upload_progress(progress, sent, total, phase):
    if progress:
        progress(sent, total, phase)


def _upload_video_in_session(path, project_id, progress=None):
    """Upload MP4 bytes through presigned URLs, then wait until media is ready."""
    headers = _headers()
    total_size = path.stat().st_size
    _report_upload_progress(progress, 0, total_size, 'Preparando upload')
    created = requests.post(f'{BASE_URL}/media/upload-sessions', headers=headers,
                            json={'projectId': project_id, 'fileSizeInBytes': total_size}, timeout=60)
    _ensure_success(created, 'a abertura da sessão de upload')
    session = created.json()
    session_id = session.get('uploadSessionId')
    part_size = session.get('partSizeInBytes')
    parts = session.get('parts')
    if not session_id or not isinstance(part_size, int) or part_size <= 0 or not isinstance(parts, list) or not parts:
        raise ValueError('A WoopSocial retornou uma sessão de upload inválida.')
    expected_count = session.get('partCount')
    if expected_count != len(parts):
        raise ValueError('A WoopSocial retornou uma sessão de upload incompleta.')
    ordered_parts = sorted(parts, key=lambda item: item.get('partNumber', 0))
    sent = 0
    with path.open('rb') as file:
        for index, part in enumerate(ordered_parts):
            url = part.get('uploadUrl') if isinstance(part, dict) else None
            chunk = file.read(part_size)
            if not url or not chunk or (index < len(ordered_parts) - 1 and len(chunk) != part_size):
                raise ValueError('A WoopSocial retornou partes de upload inválidas.')
            uploaded = requests.put(url, data=chunk, timeout=600)
            _ensure_success(uploaded, f'a parte {index + 1} do upload')
            sent += len(chunk)
            _report_upload_progress(progress, sent, total_size, 'Enviando vídeo')
        if file.read(1):
            raise ValueError('A sessão de upload não contém partes suficientes para este vídeo.')
    completed = requests.post(f'{BASE_URL}/media/upload-sessions/{session_id}/complete', headers=headers, timeout=60)
    _ensure_success(completed, 'a finalização do upload')
    _report_upload_progress(progress, total_size, total_size, 'Processando vídeo')
    for _ in range(15):
        status_response = requests.get(f'{BASE_URL}/media/upload-sessions/{session_id}', headers=headers, timeout=30)
        _ensure_success(status_response, 'o processamento do upload')
        status = status_response.json()
        media_id = _media_id(status)
        if media_id:
            return media_id
        state = str(status.get('status') or '').upper() if isinstance(status, dict) else ''
        if state in ('FAILED', 'ABORTED'):
            raise ValueError('A WoopSocial não conseguiu processar o vídeo enviado.')
        time.sleep(2)
    raise ValueError('A WoopSocial ainda está processando o vídeo. Tente publicar novamente em alguns instantes.')


def publish(video_path, project_id, account_id, title, description, privacy, scheduled_at=None, tags=None, progress=None):
    path = Path(video_path)
    if not path.is_file():
        raise ValueError('O MP4 desta produção não está disponível.')
    title = str(title or '').strip()
    if not title:
        raise ValueError('Informe um título para o vídeo do YouTube.')
    if len(title) > 100:
        raise ValueError('O título do YouTube pode ter no máximo 100 caracteres.')
    if path.stat().st_size >= CHUNKED_UPLOAD_THRESHOLD_BYTES:
        media_id = _upload_video_in_session(path, project_id, progress)
    else:
        _report_upload_progress(progress, 0, path.stat().st_size, 'Enviando vídeo')
        with path.open('rb') as file:
            upload = requests.post(f'{BASE_URL}/media', headers=_headers(), params={'projectId': project_id}, files={'file': (path.name, file, 'video/mp4')}, timeout=600)
        _ensure_success(upload, 'o upload do vídeo')
        media_id = _media_id(upload.json())
        _report_upload_progress(progress, path.stat().st_size, path.stat().st_size, 'Processando vídeo')
    if not media_id:
        raise ValueError('A WoopSocial não devolveu o identificador da mídia enviada.')
    schedule = {'type': 'PUBLISH_NOW'} if privacy != 'scheduled' else {'type': 'SCHEDULE_FOR_LATER', 'scheduledFor': scheduled_at}
    privacy_value = 'private' if privacy == 'scheduled' else privacy
    youtube_target = {'platform': 'YOUTUBE', 'socialAccountId': account_id, 'title': title, 'privacy': privacy_value}
    if tags:
        youtube_target['tags'] = [str(tag).strip() for tag in tags if str(tag).strip()]
    body = {'content': [{'text': description, 'media': [{'type': 'MEDIA_LIBRARY', 'mediaId': media_id}]}], 'schedule': schedule,
            'socialAccounts': [youtube_target]}
    headers = {**_headers(), 'Content-Type': 'application/json'}
    _report_upload_progress(progress, path.stat().st_size, path.stat().st_size, 'Criando publicação')
    validation = requests.post(f'{BASE_URL}/posts/validate', headers=headers, json=body, timeout=60)
    _ensure_success(validation, 'a validação da publicação')
    validation_result = validation.json()
    if not validation_result.get('isValid', False):
        errors = validation_result.get('errors') or []
        messages = [str(item.get('message') or item) for item in errors if item]
        raise ValueError('WoopSocial rejeitou a publicação: ' + ('; '.join(messages) or 'payload inválido.'))
    response = requests.post(f'{BASE_URL}/posts', headers=headers, json=body, timeout=60)
    _ensure_success(response, 'a criação da publicação')
    return response.json()
