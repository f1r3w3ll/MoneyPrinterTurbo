import json
import hashlib
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from app.models.schema import CheckpointState, LongFormVideoParams, StructuredScript
from app.services.checkpoint import CheckpointManager
from app.services.script_parser import ScriptParser


def example_script():
    return StructuredScript(title='Teste', description='Descrição', total_duration_estimate=900,
        scenes=[dict(index=i, narration='Uma narração completa para esta cena.',
                     image_prompt='Paisagem colorida', duration_seconds=3) for i in range(5)])


class TemporaryDirectory(tempfile.TemporaryDirectory):
    def cleanup(self):
        # Windows can briefly defer removal after the last handle closes.
        for attempt in range(4):
            try:
                return super().cleanup()
            except OSError as exc:
                if getattr(exc, 'winerror', None) != 145 or attempt == 3:
                    raise
                time.sleep(.1)


class LongformTests(unittest.TestCase):
    def test_editorial_metadata_and_retention_fields_are_preserved(self):
        data = example_script().model_dump()
        data['metadata'] = {'editorial': {'promise': 'Entenda por que isso ainda importa.'}}
        data['scenes'][0]['narrative_role'] = 'hook'
        data['scenes'][0]['open_loop'] = 'A resposta aparece no próximo capítulo.'

        parsed = ScriptParser().parse_json_script(data)

        self.assertEqual(parsed.metadata['editorial']['promise'], 'Entenda por que isso ainda importa.')
        self.assertEqual(parsed.scenes[0].narrative_role, 'hook')
        self.assertEqual(parsed.scenes[0].open_loop, 'A resposta aparece no próximo capítulo.')

    def test_cut_transition_from_generated_script_is_normalized(self):
        data = example_script().model_dump()
        data['scenes'][0]['transition'] = 'cut'
        parsed = ScriptParser().parse_json_script(data)
        self.assertEqual(parsed.scenes[0].transition, 'none')

    def test_wipe_transition_from_generated_script_is_normalized(self):
        data = example_script().model_dump()
        data['scenes'][0]['transition'] = 'wipe'
        parsed = ScriptParser().parse_json_script(data)
        self.assertEqual(parsed.scenes[0].transition, 'slide')

    def test_fade_to_black_transition_from_generated_script_is_normalized(self):
        data = example_script().model_dump()
        data['scenes'][0]['transition'] = 'fade_to_black'
        parsed = ScriptParser().parse_json_script(data)
        self.assertEqual(parsed.scenes[0].transition, 'fade')

    def test_caption_rendering_keeps_only_current_caption(self):
        from app.services import longform_media as media
        import numpy as np
        params = LongFormVideoParams(video_subject='Teste', font_size=18)
        entries = dict(duration=2., cues=[dict(start=0., end=1., text='Primeira'), dict(start=1., end=2., text='Segunda')])
        with patch.object(media, '_caption', wraps=media._caption) as draw:
            frame = media.frame_renderer(np.zeros((90, 160, 3), dtype=np.uint8), entries, params)
            frame(0.); frame(.5)
            self.assertEqual(draw.call_count, 1)
            frame(1.5)
            self.assertEqual(draw.call_count, 2)

    def test_regenerating_audio_invalidates_old_video_before_later_failure(self):
        from app.services import longform_pipeline as pipeline
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
                                         visual_mode='ai', image_provider='sd')
            entries = {str(i): dict(index=i, audio='old.mp3', image='old.png', duration=3., cues=[]) for i in range(5)}
            entries['0']['audio'] = None
            entries['1']['image'] = None
            manager = CheckpointManager('test', tmp)
            manager.save_checkpoint(CheckpointState(task_id='test', current_phase='thumbnail', completed_scenes=[],
                generated_files={'fingerprint': hashlib.sha256(params.model_dump_json().encode()).hexdigest(),
                                 'scenes': entries, 'video': 'old.mp4'}, timestamp=1))
            with patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_image', side_effect=bool), \
                 patch.object(pipeline, 'generate_scene_audio', return_value=dict(path='new.mp3', duration=4., cues=[])), \
                 patch.object(pipeline, 'generate_scene_image', side_effect=RuntimeError('offline')):
                with self.assertRaisesRegex(RuntimeError, 'offline'):
                    pipeline.run('test', params, folder)
            self.assertNotIn('video', manager.load_checkpoint().generated_files)

    def test_long_provider_cue_is_split_into_readable_captions(self):
        from app.services.longform_media import readable_cues
        cues = readable_cues([dict(start=2., end=12., text=' '.join(['palavra'] * 100))])
        self.assertGreater(len(cues), 5)
        self.assertEqual(cues[0]['start'], 2.)
        self.assertEqual(cues[-1]['end'], 12.)
        self.assertTrue(all(len(cue['text'].split()) <= 12 for cue in cues))

    def test_checkpoint_replacement_preserves_previous_on_failure(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            manager = CheckpointManager('test', tmp)
            state = CheckpointState(task_id='test', current_phase='audio', completed_scenes=[],
                                    generated_files={}, timestamp=1)
            manager.save_checkpoint(state)
            state.current_phase = 'images'
            with patch('os.replace', side_effect=OSError('disk')), patch('os.rename', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    manager.save_checkpoint(state)
            self.assertEqual(manager.load_checkpoint().current_phase, 'audio')

    def test_stock_production_keeps_clip_provenance_without_generating_images(self):
        from app.services import longform_pipeline as pipeline
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
                visual_mode='stock', stock_provider='pexels')
            def audio(scene, _params, target):
                Path(target).write_bytes(b'audio')
                return {'path': str(target), 'duration': 3., 'cues': []}
            def stock(scene, _params, _target):
                return {'path': f'clip-{scene.index}.mp4', 'provider': 'pexels',
                        'source_url': f'https://video.example/{scene.index}', 'search_term': 'data center'}
            with patch.object(pipeline, 'generate_scene_audio', side_effect=audio), \
                 patch.object(pipeline, 'fetch_scene_clip', side_effect=stock), \
                 patch.object(pipeline, 'generate_scene_image') as images, \
                 patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_stock_video', side_effect=bool):
                result = pipeline.run('stock-test', params, folder, stop_at='images')
            images.assert_not_called()
            self.assertEqual(len(result['stock_sources']), 5)
            self.assertEqual(result['stock_sources'][0]['provider'], 'pexels')

    def test_stock_thumbnail_uses_a_clip_frame_without_calling_ai_images(self):
        from app.services.longform_media import make_thumbnail
        from app.services.thumbnail import ThumbnailService

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            target = folder / 'thumbnail.jpg'
            target.write_bytes(b'image')
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
                                         visual_mode='stock', thumbnail_text='CLIP FRAME')
            with patch.object(ThumbnailService, 'generate_thumbnail_from_video', return_value=str(target)) as stock_thumbnail, \
                 patch.object(ThumbnailService, 'generate_hybrid_thumbnail') as ai_thumbnail, \
                 patch('app.services.thumbnail.ImageGenerationService') as image_service, \
                 patch.object(__import__('app.services.longform_media', fromlist=['valid_image']), 'valid_image', return_value=True):
                result = make_thumbnail(params.structured_script, params, folder, stock_video='first-clip.mp4')

            self.assertEqual(result, str(target))
            stock_thumbnail.assert_called_once()
            ai_thumbnail.assert_not_called()
            image_service.assert_not_called()

    def test_ai_credit_exhaustion_uses_stock_clips_for_the_affected_scenes(self):
        from app.services import longform_pipeline as pipeline

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
                visual_mode='ai', image_provider='sd', stock_provider='pexels')
            def audio(scene, _params, target):
                Path(target).write_bytes(b'audio')
                return {'path': str(target), 'duration': 3., 'cues': []}
            def stock(scene, _params, _target):
                return {'path': f'clip-{scene.index}.mp4', 'provider': 'pexels',
                        'source_url': f'https://video.example/{scene.index}', 'search_term': 'technology'}
            with patch.object(pipeline, 'generate_scene_audio', side_effect=audio), \
                 patch.object(pipeline, 'generate_scene_image', side_effect=RuntimeError('As fontes de imagem estão sem créditos: sd.')), \
                 patch.object(pipeline, 'fetch_scene_clip', side_effect=stock) as clips, \
                 patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_image', return_value=False), \
                 patch.object(pipeline, 'valid_stock_video', side_effect=bool):
                result = pipeline.run('credit-stock', params, folder, stop_at='images')

            self.assertEqual(clips.call_count, 5)
            self.assertEqual(len(result['stock_videos']), 5)

    def test_duplicate_scene_indices_rejected(self):
        script = example_script()
        script.scenes[1].index = 0
        with self.assertRaises(ValueError):
            ScriptParser().parse_json_script(script.model_dump())

    def test_full_pipeline_resume_after_thumbnail_failure(self):
        from app.services import longform_pipeline as pipeline
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
                                         visual_mode='ai', image_provider='sd',
                                         voice_name='pt-BR-FranciscaNeural', video_aspect='16:9')
            def audio(scene, params, target):
                Path(target).write_bytes(b'audio')
                return {'path': str(target), 'duration': 3., 'cues': [{'start': 0., 'end': 3., 'text': scene.narration}]}
            def picture(scene, params, target):
                Path(target).write_bytes(b'image')
                return str(target)
            def compose(*args, **kwargs):
                output = folder / 'final.mp4'
                output.write_bytes(b'video')
                return str(output)
            def thumbnail(*args):
                target = folder / 'thumbnail.jpg'
                target.write_bytes(b'thumbnail')
                return str(target)
            with patch.object(pipeline, 'generate_scene_audio', side_effect=audio) as speech, \
                 patch.object(pipeline, 'generate_scene_image', side_effect=picture), \
                 patch.object(pipeline, 'compose', side_effect=compose), \
                 patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_image', side_effect=bool), \
                 patch.object(pipeline, 'valid_video', side_effect=lambda value, **kw: bool(value)), \
                 patch.object(pipeline, 'make_thumbnail', side_effect=RuntimeError('thumbnail failed')):
                with self.assertRaisesRegex(RuntimeError, 'thumbnail failed'):
                    pipeline.run('test', params, folder)
                self.assertEqual(speech.call_count, 5)
            with patch.object(pipeline, 'generate_scene_audio') as speech, \
                 patch.object(pipeline, 'compose') as render, \
                 patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_image', side_effect=bool), \
                 patch.object(pipeline, 'valid_video', side_effect=lambda value, **kw: bool(value)), \
                 patch.object(pipeline, 'make_thumbnail', side_effect=thumbnail):
                result = pipeline.run('test', params, folder)
                speech.assert_not_called()
                render.assert_not_called()
                self.assertTrue(Path(result['thumbnail']).is_file())
                self.assertEqual(result['duration_seconds'], 15.)
                self.assertIn('00:00:12,000 --> 00:00:15,000', Path(result['subtitles']).read_text(encoding='utf-8'))

    def test_synthetic_video_has_measured_audio_duration(self):
        from app.services.longform_media import compose, valid_video
        from PIL import Image
        from moviepy import VideoFileClip
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            audio_path = folder / 'scene.wav'
            with wave.open(str(audio_path), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
                out.writeframes(b'\x00\x00' * 16000)
            picture = folder / 'scene.png'
            Image.new('RGB', (160, 90), '#147d92').save(picture)
            params = LongFormVideoParams(video_subject='Teste', video_aspect='16:9', bgm_type='', font_size=18)
            entries = [{'index': 0, 'image': str(picture), 'audio': str(audio_path), 'duration': 1.,
                        'cues': [{'start': 0., 'end': 1., 'text': 'Olá mundo'}]}]
            result = compose(entries, params, folder, output_name='teste.mp4', resolution=(160, 90), fps=12)
            self.assertTrue(valid_video(result))
            self.assertEqual(Path(result).name, 'teste.mp4')
            with VideoFileClip(result) as clip:
                self.assertAlmostEqual(clip.duration, 1., delta=.15)
                self.assertIsNotNone(clip.audio)
                self.assertEqual(clip.size, [160, 90])
            self.assertFalse(valid_video(result, expected_duration=10.))

    def test_stock_clip_is_composed_with_the_scene_narration(self):
        from app.services.longform_media import compose, valid_video
        from moviepy import ColorClip, VideoFileClip
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            audio_path = folder / 'scene.wav'
            with wave.open(str(audio_path), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
                out.writeframes(b'\x00\x00' * 16000)
            stock_path = folder / 'stock.mp4'
            source = ColorClip((160, 90), color=(28, 104, 154), duration=.5)
            source.write_videofile(str(stock_path), fps=12, codec='libx264', audio=False, logger=None)
            source.close()
            params = LongFormVideoParams(video_subject='Teste', video_aspect='16:9', bgm_type='', font_size=18)
            result = compose([{'index': 0, 'stock_video': str(stock_path), 'audio': str(audio_path),
                               'duration': 1., 'cues': []}], params, folder,
                             output_name='stock-final.mp4', resolution=(160, 90), fps=12)
            self.assertTrue(valid_video(result))
            with VideoFileClip(result) as clip:
                self.assertAlmostEqual(clip.duration, 1., delta=.15)
                self.assertEqual(clip.size, [160, 90])

    def test_text_cta_appends_a_logo_endcard(self):
        from app.services.longform_media import append_cta, valid_video
        from PIL import Image
        from moviepy import AudioClip, ColorClip, VideoFileClip

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            source = folder / 'source.mp4'
            logo = folder / 'logo.png'
            Image.new('RGBA', (80, 80), '#20b7a4').save(logo)
            audio = AudioClip(lambda t: 0 * t, duration=1, fps=8000)
            clip = ColorClip((90, 160), color=(16, 40, 70), duration=1).with_audio(audio)
            clip.write_videofile(str(source), fps=12, codec='libx264', audio_codec='aac', logger=None)
            clip.close(); audio.close()
            params = LongFormVideoParams(
                video_subject='Teste', cta_mode='text', cta_text='Subscribe for more',
                channel_logo_path=str(logo), bgm_type='',
            )

            result = append_cta(str(source), params, folder, fps=12)

            self.assertTrue(valid_video(result))
            with VideoFileClip(result) as rendered:
                self.assertAlmostEqual(rendered.duration, 6., delta=.3)
                self.assertEqual(rendered.size, [90, 160])
            with VideoFileClip(str(source)) as original:
                self.assertAlmostEqual(original.duration, 1., delta=.2)

    def test_pipeline_appends_configured_cta_after_composition(self):
        from app.services import longform_pipeline as pipeline
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            folder = Path(tmp)
            params = LongFormVideoParams(
                video_subject='Teste', structured_script=example_script(), visual_mode='ai', image_provider='sd', cta_mode='text',
                cta_text='Subscribe', bgm_type='',
            )
            params.structured_script.scenes[0].transition = 'fade'
            def audio(scene, _params, target):
                Path(target).write_bytes(b'audio')
                return {'path': str(target), 'duration': 3., 'cues': []}
            def image(scene, _params, target):
                Path(target).write_bytes(b'image')
                return str(target)
            def render(*_args, **_kwargs):
                target = folder / 'final.mp4'
                target.write_bytes(b'video')
                return str(target)
            with patch.object(pipeline, 'generate_scene_audio', side_effect=audio), \
                 patch.object(pipeline, 'generate_scene_image', side_effect=image), \
                 patch.object(pipeline, 'compose', side_effect=render) as composition, \
                 patch.object(pipeline, 'valid_audio', side_effect=bool), \
                 patch.object(pipeline, 'valid_image', side_effect=bool), \
                 patch.object(pipeline, 'valid_video', side_effect=lambda value, **_kw: bool(value)), \
                 patch.object(pipeline, 'append_cta', side_effect=[RuntimeError('CTA failed'), str(folder / 'final.mp4')]) as append:
                with self.assertRaisesRegex(RuntimeError, 'CTA failed'):
                    pipeline.run('test-cta', params, folder, stop_at='video')
                self.assertEqual(composition.call_args.args[0][0]['transition'], 'fade')
                composition.reset_mock()
                result = pipeline.run('test-cta', params, folder, stop_at='video')
                self.assertEqual(result['duration_seconds'], 20.)
                composition.assert_not_called()
                pipeline.run('test-cta', params, folder, stop_at='video')
                composition.assert_not_called()
            self.assertEqual(append.call_count, 2)


if __name__ == '__main__':
    unittest.main()
