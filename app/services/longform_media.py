"""Media operations for the studio; each scene owns its measured audio timeline."""
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy import AudioFileClip, VideoClip, VideoFileClip, concatenate_videoclips

from app.config import config
from app.utils import utils


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
                      voice_file=str(target))
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


def generate_scene_image(scene, params, target):
    from app.services.image_generation import ImageGenerationService
    service = ImageGenerationService(params.image_provider)
    result = service.generate_image(scene.image_prompt, Path(target).stem, str(Path(target).parent),
                                    quality=params.image_quality, size=params.image_size)
    if not valid_image(result):
        raise RuntimeError(f'Imagem inválida na cena {scene.index + 1}.')
    return result


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
        if not valid_image(entry['image']) or not valid_audio(entry['audio']):
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
            video._write_videofile_with_codec_fallback(joined, str(output), codec='libx264',
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


def make_thumbnail(script, params, folder):
    from app.services.thumbnail import ThumbnailService
    result = ThumbnailService().generate_hybrid_thumbnail(
        video_title=params.thumbnail_text or script.title,
        ai_image_prompt=script.scenes[0].image_prompt,
        output_path=str(Path(folder) / 'thumbnail.jpg'),
        style=params.thumbnail_style if params.thumbnail_style in ('dramatic', 'clean', 'colorful') else 'dramatic',
        provider=params.image_provider)
    if not valid_image(result):
        raise RuntimeError('A thumbnail não foi gerada corretamente.')
    return result
