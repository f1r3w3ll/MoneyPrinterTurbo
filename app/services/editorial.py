"""Channel identity, editorial briefs, and promise-aligned packaging helpers."""
from pathlib import Path

from app.config import config
from app.services.studio_storage import write_json

ROOT = Path(config.root_dir) / 'storage' / 'studio'
PROFILE_FILE = 'channel_profile.json'

PROFILE_DEFAULTS = {
    'name': '', 'niche': '', 'subniche': '', 'audience': '', 'promise': '',
    'tone': 'documentary', 'pillars': '', 'visual_style': '', 'source_policy': '',
    'restricted_topics': '',
}


def _clean(values, defaults):
    values = values or {}
    return {key: str(values.get(key, default)).strip() for key, default in defaults.items()}


def _profile_path():
    return ROOT / PROFILE_FILE


def get_channel_profile():
    path = _profile_path()
    if not path.is_file():
        return dict(PROFILE_DEFAULTS)
    try:
        import json
        with path.open(encoding='utf-8') as file:
            return _clean(json.load(file), PROFILE_DEFAULTS)
    except (OSError, ValueError):
        return dict(PROFILE_DEFAULTS)


def save_channel_profile(values):
    profile = _clean(values, PROFILE_DEFAULTS)
    write_json(_profile_path(), profile)
    return profile


def packaging_options(brief):
    """Return distinct, editable packaging hypotheses before spending on generation."""
    brief = brief or {}
    topic = str(brief.get('topic') or 'Este tema').strip()
    question = str(brief.get('central_question') or f'Por que {topic} importa?').strip()
    thesis = str(brief.get('thesis') or topic).strip()
    promise = str(brief.get('promise') or question).strip()
    return [
        {'title': question, 'thumbnail_text': topic[:38],
         'visual_concept': f'Contraste visual que revela: {thesis}', 'promise': promise,
         'angle': 'Pergunta central'},
        {'title': f'O que realmente aconteceu em {topic}', 'thumbnail_text': 'O QUE MUDOU?',
         'visual_concept': f'Antes e depois que sustenta a tese: {thesis}', 'promise': promise,
         'angle': 'Revelação'},
        {'title': f'Como {topic} ainda afeta você', 'thumbnail_text': 'AINDA IMPORTA',
         'visual_concept': f'Conexão entre {topic} e uma consequência atual', 'promise': promise,
         'angle': 'Consequência atual'},
    ]
