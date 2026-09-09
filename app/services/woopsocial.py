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


def youtube_accounts():
    response = requests.get(f'{BASE_URL}/social-accounts', headers=_headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()
    values = payload.get('data', payload) if isinstance(payload, dict) else payload
    if isinstance(values, dict):
        values = values.get('items') or values.get('socialAccounts') or []
    if not isinstance(values, list):
        raise ValueError('A WoopSocial retornou uma lista de canais em formato inválido.')
    return [item for item in values if isinstance(item, dict) and str(item.get('platform', '')).upper() == 'YOUTUBE']


def projects():
    response = requests.get(f'{BASE_URL}/projects', headers=_headers(), timeout=30)
    response.raise_for_status()
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


def publish(video_path, project_id, account_id, title, description, privacy, scheduled_at=None):
    path = Path(video_path)
    if not path.is_file():
        raise ValueError('O MP4 desta produção não está disponível.')
    with path.open('rb') as file:
        upload = requests.post(f'{BASE_URL}/media', headers=_headers(), params={'projectId': project_id}, files={'file': (path.name, file, 'video/mp4')}, timeout=600)
    upload.raise_for_status()
    media_id = upload.json().get('id') or upload.json().get('data', {}).get('id')
    schedule = {'type': 'PUBLISH_NOW'} if privacy != 'scheduled' else {'type': 'SCHEDULE_FOR_LATER', 'scheduledFor': scheduled_at}
    privacy_value = 'private' if privacy == 'scheduled' else privacy
    body = {'content': [{'text': description, 'media': [{'type': 'MEDIA_LIBRARY', 'mediaId': media_id}]}], 'schedule': schedule,
            'socialAccounts': [{'platform': 'YOUTUBE', 'socialAccountId': account_id, 'title': title, 'privacy': privacy_value}]}
    response = requests.post(f'{BASE_URL}/posts', headers={**_headers(), 'Content-Type': 'application/json'}, json=body, timeout=60)
    response.raise_for_status()
    return response.json()
