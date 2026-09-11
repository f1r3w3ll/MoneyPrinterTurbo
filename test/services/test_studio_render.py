"""Full local render: fake only external generation, real persistence and media."""
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from moviepy import VideoFileClip
from app.models.schema import LongFormVideoParams
from app.services import studio, longform_pipeline, longform_media
from app.services.thumbnail import ThumbnailService
from test.services.test_longform_pipeline import example_script


class StudioRenderTest(unittest.TestCase):
    @staticmethod
    def _write_silent_audio(target, seconds=1.):
        with wave.open(str(target), 'wb') as file:
            sample_rate = 16000
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(sample_rate)
            file.writeframes(b'\x00\x00' * round(sample_rate * seconds))

    @staticmethod
    def _asymmetric_image(target):
        image = Image.new('RGB', (160, 90), '#12243a')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 42, 89), fill='#f4c542')
        draw.ellipse((106, 12, 151, 62), fill='#e84a5f')
        image.save(target)

    def test_animated_image_changes_frame_without_changing_scene_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image, audio = root / 'scene.png', root / 'scene.wav'
            self._asymmetric_image(image)
            self._write_silent_audio(audio)
            params = LongFormVideoParams(video_subject='Movimento', subtitle_enabled=False,
                                         chunk_size_minutes=5, n_threads=1)
            output = longform_media.compose([
                dict(index=0, image=str(image), audio=str(audio), duration=1., cues=[], transition='none'),
            ], params, root, output_name='motion.mp4', resolution=(160, 90), fps=12)
            with VideoFileClip(output) as clip:
                self.assertAlmostEqual(clip.duration, 1., delta=.15)
                self.assertIsNotNone(clip.audio)
                first, last = clip.get_frame(.05), clip.get_frame(.80)
                self.assertGreater(np.abs(first.astype(int) - last.astype(int)).mean(), 2.)

    def test_intro_uses_stronger_motion_than_regular_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image, first_audio, second_audio = root / 'scene.png', root / 'first.wav', root / 'second.wav'
            self._asymmetric_image(image)
            self._write_silent_audio(first_audio)
            self._write_silent_audio(second_audio)
            params = LongFormVideoParams(video_subject='Abertura', subtitle_enabled=False,
                                         animated_intro=True, chunk_size_minutes=5, n_threads=1)
            output = longform_media.compose([
                dict(index=0, image=str(image), audio=str(first_audio), duration=1., cues=[], transition='none'),
                dict(index=3, image=str(image), audio=str(second_audio), duration=1., cues=[], transition='none'),
            ], params, root, output_name='intro.mp4', resolution=(160, 90), fps=12)
            with VideoFileClip(output) as clip:
                intro_motion = np.abs(clip.get_frame(.05).astype(int) - clip.get_frame(.80).astype(int)).mean()
                regular_motion = np.abs(clip.get_frame(1.05).astype(int) - clip.get_frame(1.80).astype(int)).mean()
                self.assertGreater(intro_motion, regular_motion + 1.)

    def test_fade_transition_dims_scene_end_before_the_next_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image, audio = root / 'scene.png', root / 'scene.wav'
            self._asymmetric_image(image)
            self._write_silent_audio(audio)
            params = LongFormVideoParams(video_subject='Transição', subtitle_enabled=False,
                                         chunk_size_minutes=5, n_threads=1)
            output = longform_media.compose([
                dict(index=0, image=str(image), audio=str(audio), duration=1., cues=[], transition='fade'),
            ], params, root, output_name='fade.mp4', resolution=(160, 90), fps=12)
            with VideoFileClip(output) as clip:
                middle_luminance = clip.get_frame(.50).mean()
                ending_luminance = clip.get_frame(.98).mean()
                self.assertLess(ending_luminance, middle_luminance * .75)
    def test_complete_production_has_video_thumbnail_script_and_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def speech(scene, params, target):
                target = Path(target).with_suffix('.wav')
                with wave.open(str(target), 'wb') as file:
                    file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000)
                    file.writeframes(b'\x00\x00' * 16000)
                return dict(path=str(target), duration=1., cues=[dict(start=0., end=1., text=f'Cena {scene.index + 1}')])
            def picture(scene, params, target):
                Image.new('RGB', (320, 180), (20 + scene.index * 30, 70, 110)).save(target)
                return str(target)
            def thumbnail_base(prompt, output):
                target = Path(output).with_suffix('.png')
                Image.new('RGB', (1280, 720), '#185c78').save(target)
                return str(target)
            def compose(*args, **kwargs):
                return longform_media.compose(*args, **kwargs, resolution=(320, 180), fps=12)
            with patch.object(studio, 'ROOT', root), patch.object(studio, '_manager'), \
                 patch.object(studio, 'validate_settings', return_value=[]), \
                 patch.object(longform_pipeline, 'generate_scene_audio', side_effect=speech), \
                 patch.object(longform_pipeline, 'generate_scene_image', side_effect=picture), \
                 patch.object(longform_pipeline, 'compose', side_effect=compose), \
                 patch.object(ThumbnailService, '_generate_base_image', side_effect=thumbnail_base):
                params = LongFormVideoParams(video_subject='Teste sintético', structured_script=example_script(),
                    video_aspect='16:9', bgm_type='', font_name='MicrosoftYaHeiBold.ttc', font_size=18)
                identifier = studio.submit(params)
                studio._run(identifier)
                record = studio.get_production(identifier)
                self.assertEqual(record['status'], 'complete', record.get('error'))
                self.assertEqual(record['progress'], 100)
                for key in ('video', 'thumbnail', 'script', 'subtitles'):
                    self.assertTrue(Path(record['artifacts'][key]).is_file())
                with VideoFileClip(record['artifacts']['video']) as clip:
                    self.assertAlmostEqual(clip.duration, 5., delta=.2)
                    self.assertIsNotNone(clip.audio)
                    # Caption pixels differ from the plain source image.
                    frame = clip.get_frame(.4)
                    self.assertGreater(int(frame.max()), 180)
                with Image.open(record['artifacts']['thumbnail']) as thumb:
                    self.assertEqual(thumb.size, (1280, 720))
                self.assertLess(Path(record['artifacts']['thumbnail']).stat().st_size, 2 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
