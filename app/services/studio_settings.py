"""Studio configuration. Password fields are write-only; blank means preserve."""
import copy
import importlib.util
from pathlib import Path
import threading

from app.config import config

LOCK = threading.RLock()
PROVIDERS = ('openai', 'claude', 'gemini', 'deepseek', 'kimi', 'qwen')


def get_settings():
    with LOCK:
        llm = {}
        for name in PROVIDERS:
            item = config.llm.get(name, {})
            llm[name] = {key: item.get(key, default) for key, default in
                [('model', ''), ('base_url', ''), ('enabled', True)]}
            llm[name].update(api_key='', configured=bool(item.get('api_key')))
        image = {key: config.image_generation.get(key, default) for key, default in
                 [('default_provider', 'dalle'), ('dalle_quality', 'standard'),
                  ('dalle_size', '1024x1024'), ('sd_model', 'stability-ai/stable-diffusion-3.5-large')]}
        image.update(openai_api_key='', sd_api_key='',
            openai_configured=bool(config.image_generation.get('openai_api_key') or config.app.get('openai_api_key') or config.llm.get('openai', {}).get('api_key')),
            sd_configured=bool(config.image_generation.get('sd_api_key')))
        tts = dict(elevenlabs_api_key='', elevenlabs_configured=bool(config.premium_tts.get('elevenlabs_api_key')),
                   elevenlabs_voice_id=config.premium_tts.get('elevenlabs_voice_id', ''),
                   elevenlabs_model=config.premium_tts.get('elevenlabs_model', 'eleven_multilingual_v2'))
        woop = dict(api_key='', configured=bool(config.app.get('woopsocial_api_key')))
        stock = dict(
            pexels_api_key='', pixabay_api_key='', coverr_api_key='',
            pexels_configured=bool(config.app.get('pexels_api_keys')),
            pixabay_configured=bool(config.app.get('pixabay_api_keys')),
            coverr_configured=bool(config.app.get('coverr_api_keys')),
        )
        return dict(llm=llm, image_generation=image, premium_tts=tts, woopsocial=woop, stock=stock)


def _merge(current, values, allowed):
    result = copy.deepcopy(current)
    for key in allowed:
        if key not in values:
            continue
        value = values[key]
        if key.endswith('api_key'):
            value = str(value or '').strip()
            if not value:
                continue
            if '...' in value or '***' in value:
                raise ValueError('Informe a chave completa; valores mascarados não podem ser salvos.')
        result[key] = value
    return result


def save_settings(values):
    with LOCK:
        llm = copy.deepcopy(config.llm)
        for provider, item in values.get('llm', {}).items():
            if provider not in PROVIDERS:
                raise ValueError('Provedor de roteiro não suportado.')
            llm[provider] = _merge(llm.get(provider, {}), item, ('api_key', 'model', 'base_url', 'enabled'))
        image = _merge(config.image_generation, values.get('image_generation', {}),
                       ('default_provider', 'openai_api_key', 'sd_api_key', 'sd_model', 'dalle_model', 'dalle_quality', 'dalle_size'))
        tts = _merge(config.premium_tts, values.get('premium_tts', {}),
                     ('elevenlabs_api_key', 'elevenlabs_voice_id', 'elevenlabs_model'))
        if image.get('default_provider', 'dalle') not in ('dalle', 'sd'):
            raise ValueError('Provedor de imagens não implementado.')
        app = _merge(config.app, values.get('woopsocial', {}), ('woopsocial_api_key',))
        stock_values = values.get('stock', {})
        for provider in ('pexels', 'pixabay', 'coverr'):
            key_name = f'{provider}_api_key'
            value = str(stock_values.get(key_name, '') or '').strip()
            if not value:
                continue
            if '...' in value or '***' in value:
                raise ValueError('Informe a chave completa; valores mascarados não podem ser salvos.')
            app[f'{provider}_api_keys'] = [value]
        previous = (copy.deepcopy(config.llm), copy.deepcopy(config.image_generation), copy.deepcopy(config.premium_tts), copy.deepcopy(config.app))
        try:
            for target, value in [(config.llm, llm), (config.image_generation, image), (config.premium_tts, tts), (config.app, app)]:
                target.clear(); target.update(value)
            config.save_config()
        except Exception:
            for target, value in zip((config.llm, config.image_generation, config.premium_tts, config.app), previous):
                target.clear(); target.update(value)
            raise


def redact(message):
    text = str(message)
    def walk(value):
        nonlocal text
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and item and ('key' in key or 'token' in key or 'password' in key):
                    text = text.replace(item, '[credencial]')
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for section in (config.llm, config.image_generation, config.premium_tts, config.app):
        walk(section)
    return text[:1500]


def validate_settings(params):
    errors = []
    settings = get_settings()
    visual_mode = getattr(params, 'visual_mode', 'ai')
    if visual_mode not in ('ai', 'stock', 'hybrid'):
        errors.append('Selecione uma fonte visual válida.')
    if visual_mode in ('ai', 'hybrid'):
        if params.image_provider not in ('dalle', 'sd'):
            errors.append('Selecione DALL-E ou Stable Diffusion para as imagens.')
        elif params.image_provider == 'dalle' and not settings['image_generation']['openai_configured']:
            errors.append('Configure a chave OpenAI para gerar imagens.')
        elif params.image_provider == 'sd':
            if not settings['image_generation']['sd_configured']:
                errors.append('Configure a chave do Replicate para Stable Diffusion.')
            if importlib.util.find_spec('replicate') is None:
                errors.append('Instale as dependências atualizadas com uv sync --frozen (Replicate ausente).')
    if visual_mode in ('stock', 'hybrid'):
        provider = getattr(params, 'stock_provider', 'pexels')
        labels = {'pexels': 'Pexels', 'pixabay': 'Pixabay', 'coverr': 'Coverr'}
        if provider not in labels:
            errors.append('Selecione Pexels, Pixabay ou Coverr para os clipes gratuitos.')
        elif not settings.get('stock', {}).get(f'{provider}_configured'):
            errors.append(f'Configure uma chave {labels[provider]} para usar clipes gratuitos.')
    if not params.voice_name:
        errors.append('Selecione uma voz para a narração.')
    elif params.voice_name.startswith('elevenlabs:'):
        if not params.voice_name.removeprefix('elevenlabs:').strip():
            errors.append('Informe o identificador da voz ElevenLabs.')
        if not settings['premium_tts']['elevenlabs_configured']:
            errors.append('Configure a chave ElevenLabs.')
        if importlib.util.find_spec('elevenlabs') is None:
            errors.append('Instale as dependências atualizadas com uv sync --frozen (ElevenLabs ausente).')
    if params.premium_tts_provider and params.premium_tts_provider not in ('elevenlabs', 'edge'):
        errors.append('Este provedor de voz ainda não está implementado.')
    if params.premium_tts_provider == 'elevenlabs' and not params.voice_name.startswith('elevenlabs:'):
        errors.append('Selecione uma voz ElevenLabs para o provedor escolhido.')
    if params.cta_mode not in ('text', 'image', 'video'):
        errors.append('Selecione um formato de CTA válido.')
    if params.cta_mode in ('image', 'video'):
        asset = Path(params.cta_asset_path or '')
        accepted = {'.png', '.jpg', '.jpeg', '.webp'} if params.cta_mode == 'image' else {'.mp4', '.mov', '.webm'}
        if not asset.is_file() or asset.suffix.lower() not in accepted:
            errors.append('Envie um arquivo compatível com o CTA selecionado.')
    return errors
