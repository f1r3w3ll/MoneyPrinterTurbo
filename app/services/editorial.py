"""Channel identity, editorial briefs, and promise-aligned packaging helpers."""
import json
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

BRIEF_DEFAULTS = {
    'topic': '', 'central_question': '', 'thesis': '', 'promise': '',
    'goal': 'Descoberta', 'sources': '',
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


def _brief(values, topic=''):
    brief = _clean(values, BRIEF_DEFAULTS)
    brief['topic'] = str(topic or brief['topic']).strip()
    if brief['goal'] not in ('Descoberta', 'Busca', 'Retorno ao canal'):
        brief['goal'] = 'Descoberta'
    return brief


def brief_prompt(topic, profile):
    """Build a constrained prompt for useful, honest YouTube pre-production."""
    profile = _clean(profile, PROFILE_DEFAULTS)
    return f"""You are a YouTube editorial strategist. Create a concise, original editorial brief in Brazilian Portuguese for a long-form video.

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
