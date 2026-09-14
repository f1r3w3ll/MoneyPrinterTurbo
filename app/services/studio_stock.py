"""Free stock-clip retrieval for Studio productions."""
from pathlib import Path
import re

from app.models.schema import VideoAspect
from app.services import material
from app.services.longform_media import valid_stock_video

_SEARCHERS = {
    'pexels': material.search_videos_pexels,
    'pixabay': material.search_videos_pixabay,
    'coverr': material.search_videos_coverr,
}


def scene_search_term(scene):
    """Derive a short library query without a further paid LLM call."""
    raw = str(getattr(scene, 'visual_function', '') or getattr(scene, 'image_prompt', '') or '').strip()
    raw = re.sub(r'\b(cinematic|photorealistic|ultra[- ]?detailed|dramatic lighting|4k|8k)\b', '', raw, flags=re.I)
    raw = re.split(r'[.;:]', raw, maxsplit=1)[0]
    words = re.findall(r"[\w'-]+", raw)
    return ' '.join(words[:10]).strip() or 'technology documentary'


def fetch_scene_clip(scene, params, target_dir):
    """Search and download one usable clip, retaining its provenance."""
    provider = str(getattr(params, 'stock_provider', 'pexels') or 'pexels').lower()
    if provider not in _SEARCHERS:
        raise ValueError('Fonte de clipes não suportada.')
    term = scene_search_term(scene)
    aspect = VideoAspect(getattr(params, 'video_aspect', VideoAspect.landscape.value))
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    attempted = []
    for candidate in (provider,) + tuple(name for name in _SEARCHERS if name != provider):
        try:
            clips = _SEARCHERS[candidate](term, minimum_duration=3, video_aspect=aspect)
        except Exception:
            clips = []
        if not clips:
            attempted.append(candidate)
            continue
        for clip in clips:
            path = material.save_video(clip.url, str(target_dir))
            if valid_stock_video(path):
                return {'path': str(path), 'provider': clip.provider, 'source_url': clip.url,
                        'source_duration': clip.duration, 'search_term': term}
        attempted.append(candidate)
    names = ', '.join(attempted)
    raise RuntimeError(f'Nenhum clipe gratuito pôde ser obtido para a cena {scene.index + 1}: {term} ({names}).')
