"""WoopSocial publishing client. Credentials stay in local configuration."""
from pathlib import Path
import requests

from app.config import config

BASE_URL = 'https://api.woopsocial.com/v1'


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


def publish(video_path, project_id, account_id, title, description, privacy, scheduled_at=None, tags=None):
    path = Path(video_path)
    if not path.is_file():
        raise ValueError('O MP4 desta produção não está disponível.')
    title = str(title or '').strip()
    if not title:
        raise ValueError('Informe um título para o vídeo do YouTube.')
    if len(title) > 100:
        raise ValueError('O título do YouTube pode ter no máximo 100 caracteres.')
    with path.open('rb') as file:
        upload = requests.post(f'{BASE_URL}/media', headers=_headers(), params={'projectId': project_id}, files={'file': (path.name, file, 'video/mp4')}, timeout=600)
    _ensure_success(upload, 'o upload do vídeo')
    upload_result = upload.json()
    media_id = (upload_result.get('id') or (upload_result.get('data') or {}).get('id')
                or (upload_result.get('media') or {}).get('id'))
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
