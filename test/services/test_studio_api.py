import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from starlette.requests import Request
from fastapi import BackgroundTasks
from app.models.schema import LongFormVideoParams
from app.models.exception import HttpException
from test.services.test_longform_pipeline import example_script


class StudioAPITests(unittest.TestCase):
    def test_llm_settings_use_shared_service(self):
        from app.controllers.v1 import video
        from app.services import studio_settings
        from app.models.schema import LLMConfigUpdate
        request = Request({'type': 'http', 'headers': []})
        with patch.object(studio_settings, 'save_settings') as save, \
             patch.object(video.config, '_cfg', {}), patch.object(video.config, 'save_config'):
            video.update_llm_config(request, LLMConfigUpdate(configs=[dict(provider='openai', api_key='test')]))
            self.assertEqual(save.call_args.args[0]['llm']['openai']['api_key'], 'test')

    def test_creation_uses_complete_persistent_pipeline(self):
        from app.controllers.v1 import video
        from app.services import studio
        request = Request({'type': 'http', 'headers': []})
        with patch.object(studio, 'submit', return_value='production-id') as submit, patch.object(video.task_manager, 'add_task'):
            response = video.create_longform_video(BackgroundTasks(), request,
                LongFormVideoParams(video_subject='Teste', structured_script=example_script()))
            self.assertEqual(response['data']['task_id'], 'production-id')
            submit.assert_called_once()

    def test_resume_requires_only_saved_identifier(self):
        from app.controllers.v1 import video
        from app.services import studio
        request = Request({'type': 'http', 'headers': []})
        with patch.object(studio, 'resume', return_value='production-id') as resume:
            response = video.resume_longform_task(BackgroundTasks(), request, 'production-id', None)
            self.assertEqual(response['data']['task_id'], 'production-id')
            resume.assert_called_once_with('production-id')

    def test_missing_script_is_400(self):
        from app.controllers.v1 import video
        request = Request({'type': 'http', 'headers': []})
        with self.assertRaises(HttpException) as failure:
            video.create_longform_video(BackgroundTasks(), request, LongFormVideoParams(video_subject='Teste'))
        self.assertEqual(failure.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
