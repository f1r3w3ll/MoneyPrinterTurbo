"""Channel identity, editorial briefs, and promise-aligned packaging helpers."""
import json
from pathlib import Path
import re
import unicodedata

from app.config import config
from app.services.studio_storage import write_json

ROOT = Path(config.root_dir) / 'storage' / 'studio'
PROFILE_FILE = 'channel_profile.json'
CHANNELS_DIR = 'channels'
CHANNEL_INDEX_FILE = 'channels.json'

PROFILE_DEFAULTS = {
    'name': '', 'niche': '', 'subniche': '', 'audience': '', 'promise': '',
    'language': 'pt-BR', 'tone': 'documentary', 'pillars': '', 'visual_style': '', 'source_policy': '',
    'restricted_topics': '',
    'default_cta': '',
}

FIRST_CHANNEL_ID = 'fio-da-ciencia'
FIRST_CHANNEL_PROFILE = {
    'name': 'Fio da Ciência',
    'niche': 'Science and technology explained',
    'subniche': 'Ideas, infrastructure and discoveries that transform everyday life',
    'audience': 'Curious adults aged 20–45 who want to understand the world without empty simplification',
    'promise': 'Explain clearly how science and technology shape the world, from the idea to its practical consequences.',
    'language': 'en-US',
    'tone': 'documentary',
    'pillars': 'Invisible technologies; history of discoveries; large systems; human dilemmas and consequences',
    'visual_style': 'Cinematic documentary, archives, clean diagrams and visual comparisons that reveal scale and cause',
    'source_policy': 'Prioritize primary sources, scientific institutions, technical documentation and reliable reviews; state uncertainty and dates.',
    'restricted_topics': 'Sensationalism, evidence-free future claims, pseudoscience, alarmism, and medical, financial or safety advice without qualified sources.',
    'default_cta': '',
}

BRIEF_DEFAULTS = {
    'topic': '', 'central_question': '', 'thesis': '', 'promise': '',
    'goal': 'Descoberta', 'sources': '',
}


def _clean(values, defaults):
    values = values or {}
    return {key: str(values.get(key, default)).strip() for key, default in defaults.items()}


def _legacy_profile_path():
    return ROOT / PROFILE_FILE


def _index_path():
    return ROOT / CHANNEL_INDEX_FILE


def _channel_path(channel_id):
    return ROOT / CHANNELS_DIR / f'{channel_id}.json'


def _read_json(path, fallback):
    try:
        with path.open(encoding='utf-8') as file:
            return json.load(file)
    except (OSError, ValueError):
        return fallback


def _channel_id(name):
    normalized = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode().lower()
    value = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')
    return value or 'canal'


def _ensure_channels():
    index_path = _index_path()
    index = _read_json(index_path, None)
    if isinstance(index, dict) and index.get('channels'):
        return index

    legacy = _read_json(_legacy_profile_path(), {})
    legacy_profile = _clean(legacy, PROFILE_DEFAULTS)
    if isinstance(legacy, dict) and any(str(value).strip() for key, value in legacy.items() if key != 'tone'):
        channel_id = _channel_id(legacy_profile['name'])
        profile = legacy_profile
    else:
        channel_id = FIRST_CHANNEL_ID
        profile = _clean(FIRST_CHANNEL_PROFILE, PROFILE_DEFAULTS)
    write_json(_channel_path(channel_id), profile)
    index = {
        'active_channel_id': channel_id,
        'channels': [{'id': channel_id, 'name': profile['name'], 'niche': profile['niche']}],
    }
    write_json(index_path, index)
    return index


def list_channels():
    """Return the available channels without their full editorial data."""
    return list(_ensure_channels()['channels'])


def active_channel_id():
    return _ensure_channels()['active_channel_id']


def set_active_channel(channel_id):
    index = _ensure_channels()
    channel_id = str(channel_id)
    if channel_id not in {channel['id'] for channel in index['channels']}:
        raise ValueError('Canal não encontrado.')
    index['active_channel_id'] = channel_id
    write_json(_index_path(), index)
    return channel_id


def get_channel_profile(channel_id=None):
    index = _ensure_channels()
    channel_id = str(channel_id or index['active_channel_id'])
    if channel_id not in {channel['id'] for channel in index['channels']}:
        raise ValueError('Canal não encontrado.')
    return _clean(_read_json(_channel_path(channel_id), {}), PROFILE_DEFAULTS)


def create_channel(values):
    """Create an independent, editable channel profile and make it active."""
    index = _ensure_channels()
    profile = _clean(values, PROFILE_DEFAULTS)
    if not profile['name']:
        raise ValueError('Informe o nome do canal.')
    candidate = _channel_id(profile['name'])
    known = {channel['id'] for channel in index['channels']}
    channel_id = candidate
    suffix = 2
    while channel_id in known:
        channel_id = f'{candidate}-{suffix}'
        suffix += 1
    write_json(_channel_path(channel_id), profile)
    index['channels'].append({'id': channel_id, 'name': profile['name'], 'niche': profile['niche']})
    index['active_channel_id'] = channel_id
    write_json(_index_path(), index)
    return {'id': channel_id, **profile}


def save_channel_profile(values):
    profile = _clean(values, PROFILE_DEFAULTS)
    index = _ensure_channels()
    channel_id = index['active_channel_id']
    write_json(_channel_path(channel_id), profile)
    for channel in index['channels']:
        if channel['id'] == channel_id:
            channel.update(name=profile['name'], niche=profile['niche'])
            break
    write_json(_index_path(), index)
    return profile


def _brief(values, topic=''):
    brief = _clean(values, BRIEF_DEFAULTS)
    brief['topic'] = str(topic or brief['topic']).strip()
    if brief['goal'] not in ('Descoberta', 'Busca', 'Retorno ao canal'):
        brief['goal'] = 'Descoberta'
    return brief


def brief_prompt(topic, profile):
    """Build a constrained prompt for useful, honest YouTube pre-production."""
    profile = _clean(profile, PROFILE_DEFAULTS)
    language_names = {'pt-BR': 'Brazilian Portuguese', 'en-US': 'English', 'de-DE': 'German', 'es-ES': 'Spanish'}
    language = language_names.get(profile['language'], profile['language'])
    return f"""You are a YouTube editorial strategist. Create a concise, original editorial brief in {language} for a long-form video.

Topic: {topic}
Channel profile: {json.dumps(profile, ensure_ascii=False)}

Apply these rules:
- Find one specific viewer question and one defensible thesis, not a generic summary.
- The promise must be specific, answerable in the video, and free of sensational or misleading claims.
- Favor curiosity through a genuine tension, contradiction, consequence, or unanswered question.
- Consider the target audience and the channel promise; do not invent facts, statistics, or sources.
- Suggest verification directions instead of asserting unverified claims. Preserve the channel restrictions and source policy.
- Choose one goal exactly: Descoberta, Busca, or Retorno ao canal.

Return JSON only, with exactly these fields:
{{
  "central_question": "...",
  "thesis": "...",
  "promise": "...",
  "goal": "Descoberta | Busca | Retorno ao canal",
  "sources": "Verification leads and source types to check"
}}"""


def generate_brief(topic, profile, provider):
    """Create editable brief fields using the same configured LLM as the Studio."""
    topic = str(topic or '').strip()
    if not topic:
        raise ValueError('Informe o tema do vídeo antes de gerar a pauta.')
    from app.services.script_generator import ScriptGeneratorService

    content = ScriptGeneratorService().generate_editorial_json(provider, brief_prompt(topic, profile))
    content = content.strip()
    if content.startswith('```json'):
        content = content[7:]
    if content.startswith('```'):
        content = content[3:]
    if content.endswith('```'):
        content = content[:-3]
    try:
        values = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f'A IA retornou uma pauta inválida: {exc}') from exc
    if not isinstance(values, dict):
        raise ValueError('A IA retornou uma pauta inválida.')
    return _brief(values, topic)


def packaging_options(brief, language='pt-BR'):
    """Return distinct, editable packaging hypotheses before spending on generation."""
    brief = brief or {}
    topic = str(brief.get('topic') or 'Este tema').strip()
    question = str(brief.get('central_question') or f'Por que {topic} importa?').strip()
    thesis = str(brief.get('thesis') or topic).strip()
    promise = str(brief.get('promise') or question).strip()
    title_topic = _shorten_text(topic, 44)
    title_question = _shorten_text(question, 70)
    thumbnail_topic = _shorten_text(topic, 38)
    if language == 'en-US':
        return [
            {'title': title_question, 'thumbnail_text': thumbnail_topic,
             'visual_concept': f'Visual contrast that reveals: {thesis}', 'promise': promise,
             'angle': 'Central question'},
            {'title': f'What really happened in {title_topic}', 'thumbnail_text': 'WHAT CHANGED?',
             'visual_concept': f'Before-and-after evidence for the thesis: {thesis}', 'promise': promise,
             'angle': 'Reveal'},
            {'title': f'How {title_topic} still affects you', 'thumbnail_text': 'STILL MATTERS',
             'visual_concept': f'Connect {topic} to a present-day consequence', 'promise': promise,
             'angle': 'Present consequence'},
        ]
    if language == 'es-ES':
        return [
            {'title': title_question, 'thumbnail_text': thumbnail_topic,
             'visual_concept': f'Contraste visual que revela: {thesis}', 'promise': promise,
             'angle': 'Pregunta central'},
            {'title': f'Lo que realmente ocurrió en {_shorten_text(topic, 40)}', 'thumbnail_text': '¿QUÉ CAMBIÓ?',
             'visual_concept': f'Antes y después que respalda la tesis: {thesis}', 'promise': promise,
             'angle': 'Revelación'},
            {'title': f'Cómo {_shorten_text(topic, 43)} todavía te afecta', 'thumbnail_text': 'AÚN IMPORTA',
             'visual_concept': f'Conexión entre {topic} y una consecuencia actual', 'promise': promise,
             'angle': 'Consecuencia actual'},
        ]
    if language == 'de-DE':
        return [
            {'title': title_question, 'thumbnail_text': thumbnail_topic,
             'visual_concept': f'Visueller Kontrast, der zeigt: {thesis}', 'promise': promise,
             'angle': 'Zentrale Frage'},
            {'title': f'Was wirklich geschah bei {_shorten_text(topic, 40)}', 'thumbnail_text': 'WAS ÄNDERTE SICH?',
             'visual_concept': f'Vorher und nachher als Beleg für die These: {thesis}', 'promise': promise,
             'angle': 'Enthüllung'},
            {'title': f'Wie {_shorten_text(topic, 43)} dich heute noch betrifft', 'thumbnail_text': 'IMMER NOCH WICHTIG',
             'visual_concept': f'Verbindung zwischen {topic} und einer heutigen Folge', 'promise': promise,
             'angle': 'Aktuelle Folge'},
        ]
    return [
        {'title': title_question, 'thumbnail_text': thumbnail_topic,
         'visual_concept': f'Contraste visual que revela: {thesis}', 'promise': promise,
         'angle': 'Pergunta central'},
        {'title': f'O que realmente aconteceu em {_shorten_text(topic, 42)}', 'thumbnail_text': 'O QUE MUDOU?',
         'visual_concept': f'Antes e depois que sustenta a tese: {thesis}', 'promise': promise,
         'angle': 'Revelação'},
        {'title': f'Como {_shorten_text(topic, 45)} ainda afeta você', 'thumbnail_text': 'AINDA IMPORTA',
         'visual_concept': f'Conexão entre {topic} e uma consequência atual', 'promise': promise,
         'angle': 'Consequência atual'},
    ]


def _shorten_text(value, limit):
    """Trim a proposed title at a word boundary while keeping it editable."""
    value = str(value or '').strip()
    if len(value) <= limit:
        return value
    shortened = value[:limit + 1].rsplit(' ', 1)[0].rstrip(' ,:;-')
    return shortened or value[:limit].rstrip()
