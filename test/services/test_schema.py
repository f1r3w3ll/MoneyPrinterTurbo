import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pydantic import ValidationError

from app.models.schema import (
    AudioRequest,
    SubtitleRequest,
    VideoAspect,
    VideoScriptRequest,
    VideoTermsRequest,
)


class TestVideoAspect(unittest.TestCase):
    def test_to_resolution_known_aspects(self):
        self.assertEqual(VideoAspect.landscape.to_resolution(), (1920, 1080))
        self.assertEqual(VideoAspect.portrait.to_resolution(), (1080, 1920))
        self.assertEqual(VideoAspect.square.to_resolution(), (1080, 1080))

    def test_to_resolution_rejects_unsupported_value(self):
        with self.assertRaises(ValueError):
            VideoAspect.to_resolution("4:5")


class TestRequestModels(unittest.TestCase):
    def test_video_script_request_validates_fields(self):
        body = VideoScriptRequest(video_subject="Test", paragraph_number=3)
        self.assertEqual(body.paragraph_number, 3)

        with self.assertRaises(ValidationError):
            VideoScriptRequest(video_subject="Test", paragraph_number=0)

        with self.assertRaises(ValidationError):
            VideoScriptRequest(video_subject="Test", paragraph_number=11)

        with self.assertRaises(ValidationError):
            VideoScriptRequest(
                video_subject="Test", video_script_prompt="x" * 2001
            )

    def test_video_terms_request_defaults(self):
        body = VideoTermsRequest()
        self.assertEqual(body.amount, 5)
        self.assertFalse(body.match_materials_to_script)

    def test_subtitle_and_audio_requests_share_base_fields(self):
        subtitle = SubtitleRequest(video_script="hello")
        audio = AudioRequest(video_script="hello")

        for request in (subtitle, audio):
            self.assertEqual(request.voice_name, "zh-CN-XiaoxiaoNeural-Female")
            self.assertEqual(request.voice_rate, 1.2)
            self.assertEqual(request.bgm_type, "random")
            self.assertEqual(request.video_source, "local")

        self.assertEqual(subtitle.subtitle_enabled, "true")
        self.assertEqual(subtitle.font_size, 60)
        self.assertFalse(hasattr(audio, "font_name"))


if __name__ == "__main__":
    unittest.main()
