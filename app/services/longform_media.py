"""Media operations for the studio; each scene owns its measured audio timeline."""
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy import AudioClip, AudioFileClip, VideoClip, VideoFileClip, concatenate_videoclips

from app.config import config
from app.utils import utils
from app.services.provider_errors import is_credit_exhausted


def nonempty(filename):
    return bool(filename) and Path(filename).is_file() and Path(filename).stat().st_size > 0


def valid_audio(filename):
    if not nonempty(filename):
        return False
    try:
        with AudioFileClip(str(filename)) as audio:
            return math.isfinite(audio.duration) and audio.duration > 0
    except Exception:
        return False


def valid_image(filename):
    if not nonempty(filename):
        return False
    try:
        with Image.open(filename) as picture:
            picture.verify()
        return True
    except Exception:
        return False


def valid_video(filename, expected_duration=None):
    if not nonempty(filename):
        return False
    try:
        with VideoFileClip(str(filename)) as clip:
            return (clip.duration > 0 and clip.audio is not None and
                    (expected_duration is None or abs(clip.duration - expected_duration) < 1.))
    except Exception:
        return False


def valid_stock_video(filename):
    """Stock clips do not need an audio track because narration is added later."""
    if not nonempty(filename):
        return False
    try:
        with VideoFileClip(str(filename)) as clip:
            return math.isfinite(clip.duration) and clip.duration > 0
    except Exception:
        return False


def fallback_cues(text, duration):
    words = text.split()
    groups = [' '.join(words[i:i + 12]) for i in range(0, len(words), 12)]
    total = sum(len(group) for group in groups) or 1
    cursor = 0.
    cues = []
    for group in groups:
        end = cursor + duration * len(group) / total
        cues.append(dict(start=cursor, end=min(end, duration), text=group))
        cursor = end
    return cues


def readable_cues(cues):
    result = []
    for cue in cues:
        segments = fallback_cues(cue['text'], cue['end'] - cue['start'])
        for segment in segments:
            segment['start'] += cue['start']
            segment['end'] += cue['start']
        if segments:
            segments[-1]['end'] = cue['end']
        result.extend(segments)
    return result


def generate_scene_audio(scene, params, target):
    from app.services import voice
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    maker = voice.tts(text=scene.narration, voice_name=params.voice_name,
                      voice_rate=params.voice_rate, voice_volume=params.voice_volume,
                      voice_file=str(target), detailed_errors=True)
    if maker is None or not valid_audio(target):
        raise RuntimeError(f'Não foi possível gerar a narração da cena {scene.index + 1}.')
    with AudioFileClip(str(target)) as clip:
        duration = clip.duration
    cues = []
    raw = getattr(maker, 'cues', [])
    if raw:
        # Preserve provider timing, grouping short word cues into readable lines.
        batch = []
        for cue in raw:
            batch.append(cue)
            if len(batch) >= 10 or cue.end.total_seconds() - batch[0].start.total_seconds() >= 5:
                cues.append(dict(start=max(0., batch[0].start.total_seconds()),
                                 end=min(duration, batch[-1].end.total_seconds()),
                                 text=' '.join(item.content for item in batch)))
                batch = []
        if batch:
            cues.append(dict(start=max(0., batch[0].start.total_seconds()),
                             end=min(duration, batch[-1].end.total_seconds()),
                             text=' '.join(item.content for item in batch)))
    if not cues:
        cues = fallback_cues(scene.narration, duration)
    return dict(path=str(target), duration=duration, cues=readable_cues(cues))


def _configured_image_providers(preferred):
    """Return configured non-OpenAI image providers for legacy AI productions."""
    preferred = str(preferred or 'sd')
    candidates = []
    sd_ready = bool(config.image_generation.get('sd_api_key'))
    if preferred == 'sd' and sd_ready:
        candidates.append('sd')
    return candidates


def generate_scene_image(scene, params, target):
    """Generate a scene image, switching providers only after a credit exhaustion error."""
    from app.services.image_generation import ImageGenerationService
    unavailable = []
    last_error = None
    for provider in _configured_image_providers(params.image_provider):
        try:
            service = ImageGenerationService(provider)
            result = service.generate_image(scene.image_prompt, Path(target).stem, str(Path(target).parent),
                                            quality=params.image_quality, size=params.image_size)
            if not valid_image(result):
                raise RuntimeError(f'Imagem inválida na cena {scene.index + 1}.')
            return dict(path=result, provider=provider, unavailable_providers=unavailable)
        except Exception as exc:
            if not is_credit_exhausted(exc):
                raise
            unavailable.append(provider)
            last_error = exc
    if not _configured_image_providers(params.image_provider):
        raise RuntimeError('Imagens por IA não estão disponíveis. Use o modo Pexels para não consumir créditos de imagem.')
    names = ', '.join(unavailable) or str(params.image_provider)
    raise RuntimeError(f'As fontes de imagem estão sem créditos: {names}.') from last_error


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f'{hours:02}:{minute:02}:{sec:02},{ms:03}'


def write_subtitles(entries, target):
    lines, cursor = [], 0.
    for entry in entries:
        for cue in entry['cues']:
            if cue['end'] <= cue['start']:
                continue
            lines.append(f"{len(lines) + 1}\n{timestamp(cursor + cue['start'])} --> "
                         f"{timestamp(cursor + cue['end'])}\n{cue['text']}\n")
        cursor += entry['duration']
    Path(target).write_text('\n'.join(lines), encoding='utf-8')
    return str(target)


def _caption(text, size, params):
    width, height = size
    font_path = Path(utils.root_dir()) / 'resource' / 'fonts' / Path(params.font_name or '').name
    if not font_path.is_file():
        font_path = Path(utils.root_dir()) / 'resource/fonts/MicrosoftYaHeiBold.ttc'
    font_size = max(12, min(params.font_size, height // 12))
    font = ImageFont.truetype(str(font_path), font_size)
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines, line = [], ''
    for word in text.split():
        candidate = f'{line} {word}'.strip()
        if draw.textlength(candidate, font=font) > width * .88 and line:
            lines.append(line); line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    caption = '\n'.join(lines)
    box = draw.multiline_textbbox((0, 0), caption, font=font, spacing=5)
    text_height = box[3] - box[1]
    y = {'top': height * .08, 'center': (height - text_height) / 2}.get(
        params.subtitle_position, height * .88 - text_height)
    x = (width - (box[2] - box[0])) / 2
    if params.text_background_color:
        draw.rounded_rectangle((max(0, x - 12), max(0, y - 6), min(width, width - x + 12),
                                min(height, y + text_height + 18)), radius=8, fill=(0, 0, 0, 180))
    draw.multiline_text((x, y - box[1]), caption, font=font, fill=params.text_fore_color or 'white',
                        spacing=5, align='center', stroke_width=max(0, round(params.stroke_width)),
                        stroke_fill=params.stroke_color or 'black')
    return np.asarray(image)


def motion_renderer(picture, size, entry, params):
    """Return deterministic camera motion for one still image.

    The canvas is deliberately larger than the delivered frame, allowing a
    pan-and-zoom crop without changing the scene's audio-driven duration.
    """
    width, height = size
    intro = bool(getattr(params, 'animated_intro', False)) and int(entry['index']) < 3
    transition = (entry.get('transition') or 'none').lower()
    max_zoom = 1.24 if intro else 1.10
    if transition == 'zoom':
        max_zoom += .08
    canvas_size = (math.ceil(width * max_zoom), math.ceil(height * max_zoom))
    canvas = ImageOps.fit(picture.convert('RGB'), canvas_size, method=Image.Resampling.LANCZOS)
    direction = int(entry['index']) % 4
    duration = max(.001, float(entry['duration']))

    def frame(t):
        fraction = min(1., max(0., float(t) / duration))
        zoom = 1. + (max_zoom - 1.) * fraction
        crop_width = max(1, round(width / zoom))
        crop_height = max(1, round(height / zoom))
        span_x, span_y = canvas.width - crop_width, canvas.height - crop_height
        if direction == 0:
            x, y = round(span_x * fraction), span_y // 2
        elif direction == 1:
            x, y = round(span_x * (1. - fraction)), span_y // 2
        elif direction == 2:
            x, y = span_x // 2, round(span_y * fraction)
        else:
            x, y = span_x // 2, round(span_y * (1. - fraction))
        cropped = canvas.crop((x, y, x + crop_width, y + crop_height))
        return np.asarray(cropped.resize(size, Image.Resampling.LANCZOS))

    return frame


def stock_renderer(clip, size):
    """Fit a stock clip to the production canvas and loop it for narration."""
    duration = max(.001, float(clip.duration))
    def frame(t):
        picture = Image.fromarray(clip.get_frame(float(t) % duration)).convert('RGB')
        return np.asarray(ImageOps.fit(picture, size, method=Image.Resampling.LANCZOS))
    return frame


def frame_renderer(frame_supplier, entry, params):
    """Render moving frames and cache a captioned result for one frame bucket."""
    previous, rendered = None, None
    size = None
    captions = {}
    if isinstance(frame_supplier, np.ndarray):
        base = frame_supplier
        frame_supplier = lambda _time: base
    def frame(t):
        nonlocal previous, rendered, size
        text = next((cue['text'] for cue in entry['cues'] if cue['start'] <= t < cue['end']), '') if params.subtitle_enabled else ''
        bucket = int(max(0., float(t)) * 24)
        key = (text, bucket)
        if key == previous:
            return rendered
        previous = key
        base = frame_supplier(bucket / 24.)
        size = (base.shape[1], base.shape[0])
        if not text:
            rendered = base
        else:
            if text not in captions:
                captions[text] = _caption(text, size, params)
            with Image.fromarray(base).convert('RGBA') as background:
                with Image.fromarray(captions[text]) as caption:
                    rendered = np.asarray(Image.alpha_composite(background, caption).convert('RGB'))
        return rendered
    return frame


def _apply_transition(scene, entry):
    from app.services.utils import video_effects
    transition = (entry.get('transition') or 'none').lower()
    length = min(.35, max(.08, scene.duration * .2))
    if transition == 'fade':
        return video_effects.fadeout_transition(
            video_effects.fadein_transition(scene, length), length
        )
    if transition == 'slide':
        side = ('left', 'right', 'top', 'bottom')[int(entry['index']) % 4]
        return video_effects.slidein_transition(scene, length, side)
    if transition == 'zoom':
        return video_effects.fadein_transition(scene, length)
    return scene


def compose(entries, params, folder, progress=None, output_name='final.mp4', resolution=None, fps=24):
    """Encode bounded batches, then concatenate. Never skip a missing scene."""
    from app.models.schema import VideoAspect
    from app.services import video
    folder = Path(folder)
    size = resolution or VideoAspect(params.video_aspect).to_resolution()
    limit = max(30., min(300., float(params.chunk_size_minutes or 5) * 60))
    batches, batch, duration = [], [], 0.
    for entry in entries:
        visual_is_valid = valid_stock_video(entry.get('stock_video')) or valid_image(entry.get('image'))
        if not visual_is_valid or not valid_audio(entry['audio']):
            raise RuntimeError(f"Artefato ausente ou inválido na cena {entry['index'] + 1}.")
        if batch and (duration + entry['duration'] > limit or len(batch) >= 8):
            batches.append(batch); batch, duration = [], 0.
        batch.append(entry); duration += entry['duration']
    if batch:
        batches.append(batch)
    if not batches:
        raise ValueError('Nenhuma cena para compor.')
    outputs = []
    for index, batch in enumerate(batches):
        resources, clips = [], []
        try:
            for entry in batch:
                if valid_stock_video(entry.get('stock_video')):
                    stock_clip = VideoFileClip(entry['stock_video'])
                    resources.append(stock_clip)
                    renderer = stock_renderer(stock_clip, size)
                else:
                    with Image.open(entry['image']) as picture:
                        renderer = motion_renderer(picture, size, entry, params)
                audio = AudioFileClip(entry['audio'])
                resources.append(audio)
                scene = VideoClip(frame_renderer(renderer, entry, params), duration=entry['duration']).with_audio(audio)
                scene = _apply_transition(scene, entry).with_duration(entry['duration']).with_audio(audio)
                clips.append(scene); resources.append(scene)
            joined = concatenate_videoclips(clips, method='chain')
            resources.append(joined)
            output = folder / f'render-{index:03}.mp4'
            video._write_videofile_with_codec_fallback(joined, str(output), codec=video._get_configured_video_codec(),
                fps=fps, audio_codec='aac', audio_bitrate='192k', threads=params.n_threads or 2,
                logger=None, temp_audiofile=str(folder / f'render-{index:03}.m4a'))
            outputs.append(str(output))
            if progress:
                progress((index + 1) / len(batches))
        finally:
            for resource in reversed(resources):
                video.close_clip(resource)
    final = str(folder / Path(output_name).name)
    result = video._concat_chunks_ffmpeg(outputs, final)
    if not result or not valid_video(result):
        raise RuntimeError('Falha ao finalizar o vídeo.')
    expected = sum(entry['duration'] for entry in entries)
    with VideoFileClip(result) as clip:
        if abs(clip.duration - expected) > max(1., len(entries) / fps):
            raise RuntimeError('A duração renderizada não corresponde à narração completa.')
    for output in outputs:
        os.remove(output)
    return result


def _cta_font(size):
    font_path = Path(utils.root_dir()) / 'resource/fonts/MicrosoftYaHeiBold.ttc'
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        return ImageFont.load_default()


def _cta_text_card(params, size):
    """Create the branded text CTA card, keeping the logo above the message."""
    width, height = size
    image = Image.new('RGB', size, '#07111f')
    logo_path = getattr(params, 'channel_logo_path', '')
    if valid_image(logo_path):
        with Image.open(logo_path) as logo:
            logo = logo.convert('RGBA')
            logo.thumbnail((int(width * .38), int(height * .42)), Image.Resampling.LANCZOS)
            x = (width - logo.width) // 2
            y = max(int(height * .12), (height - logo.height) // 3)
            image.paste(logo, (x, y), logo)
    message = str(getattr(params, 'cta_text', '') or '').strip()
    if not message:
        return image
    draw = ImageDraw.Draw(image)
    font = _cta_font(max(18, min(72, width // 18)))
    lines, line = [], ''
    for word in message.split():
        candidate = f'{line} {word}'.strip()
        if draw.textlength(candidate, font=font) > width * .82 and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    text = '\n'.join(lines)
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=10, align='center')
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    x = (width - text_width) / 2
    y = max(height * .62, height - text_height - height * .12)
    draw.multiline_text((x, y), text, font=font, fill='white', spacing=10, align='center',
                        stroke_width=2, stroke_fill='#000000')
    return image


def _silent_audio(duration):
    def frame(time):
        if isinstance(time, np.ndarray):
            return np.zeros((len(time), 2))
        return np.zeros(2)
    return AudioClip(frame, duration=duration, fps=44100)


def cta_duration(params):
    """Duration of the configured endcard, including the supplied clip limit."""
    mode = getattr(params, 'cta_mode', 'text')
    if mode == 'text':
        return 5. if str(getattr(params, 'cta_text', '') or '').strip() else 0.
    asset = getattr(params, 'cta_asset_path', '')
    if mode == 'image':
        if not valid_image(asset):
            raise ValueError('A imagem de CTA está ausente ou inválida.')
        return 5.
    with VideoFileClip(str(asset)) as clip:
        return min(15., clip.duration)


def append_cta(video_path, params, folder, resolution=None, fps=24):
    """Append a short branded CTA card or supplied CTA media to a completed video."""
    mode = str(getattr(params, 'cta_mode', 'text') or 'text').lower()
    text = str(getattr(params, 'cta_text', '') or '').strip()
    asset_path = str(getattr(params, 'cta_asset_path', '') or '')
    if mode == 'text' and not text:
        return video_path
    if mode == 'image' and not valid_image(asset_path):
        raise ValueError('A imagem de CTA está ausente ou inválida.')
    if mode == 'video' and not nonempty(asset_path):
        raise ValueError('O vídeo de CTA está ausente ou inválido.')
    folder = Path(folder)
    target = folder / f'{Path(video_path).stem}-with-cta.mp4'
    resources = []
    try:
        base = VideoFileClip(str(video_path))
        resources.append(base)
        size = tuple(base.size)
        if mode == 'video':
            card = VideoFileClip(asset_path)
            resources.append(card)
            duration = min(15., card.duration)
            card = card.subclipped(0, duration).resized(new_size=size)
            if card.audio is None:
                card = card.with_audio(_silent_audio(duration))
            resources.append(card)
        else:
            duration = 5.
            if mode == 'image':
                with Image.open(asset_path) as picture:
                    frame = np.asarray(ImageOps.fit(picture.convert('RGB'), size, method=Image.Resampling.LANCZOS))
            else:
                frame = np.asarray(_cta_text_card(params, size))
            card = VideoClip(lambda _time: frame, duration=duration).with_audio(_silent_audio(duration))
            resources.append(card)
        joined = concatenate_videoclips([base, card], method='compose')
        resources.append(joined)
        from app.services import video
        video._write_videofile_with_codec_fallback(joined, str(target), codec=video._get_configured_video_codec(), fps=fps,
            audio_codec='aac', audio_bitrate='192k', threads=params.n_threads or 2, logger=None,
            temp_audiofile=str(folder / f'{target.stem}.m4a'))
        if not valid_video(target):
            raise RuntimeError('A tela final de CTA não foi renderizada corretamente.')
    finally:
        for resource in reversed(resources):
            try:
                resource.close()
            except Exception:
                pass
    # Keep the composed base intact for recovery, and close readers before returning.
    return str(target)


def make_thumbnail(script, params, folder, stock_video=None):
    from app.services.thumbnail import ThumbnailService
    service = ThumbnailService()
    title = params.thumbnail_text or script.title
    target = str(Path(folder) / 'thumbnail.jpg')
    style = params.thumbnail_style if params.thumbnail_style in ('dramatic', 'clean', 'colorful') else 'dramatic'
    # Prefer a licensed stock frame whenever available. This keeps the Studio
    # thumbnail entirely inside the Pexels workflow, including legacy records.
    if stock_video:
        result = service.generate_thumbnail_from_video(stock_video, title, target, style)
    else:
        raise RuntimeError('Não há clipe Pexels disponível para criar a thumbnail. Gere novamente usando a fonte visual Pexels.')
    if not valid_image(result):
        raise RuntimeError('A thumbnail não foi gerada corretamente.')
    return result
