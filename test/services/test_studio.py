import json
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch, Mock
from app.models.schema import LongFormVideoParams
from test.services.test_longform_pipeline import example_script


class StudioTests(unittest.TestCase):
    def test_production_identifier_uses_a_readable_title_slug(self):
        from app.services.studio import production_identifier

        identifier = production_identifier('A Revolução dos Microcomputadores: O Início de Tudo')
        self.assertRegex(identifier, r'^a-revolucao-dos-microcomputadores-o-inicio-de-tudo-\d{8}-\d{6}-[0-9a-f]{8}$')

    def test_premium_voice_options_include_the_configured_presets(self):
        from webui.studio import PREMIUM_VOICE_OPTIONS

        self.assertEqual(PREMIUM_VOICE_OPTIONS, (
            ('Homem · português', 'elevenlabs:UP5aPvvfM4UCXZrr3fdX'),
            ('Mulher · português', 'elevenlabs:lWq4KDY8znfkV0DrK8Vb'),
            ('Mulher · inglês', 'elevenlabs:lWq4KDY8znfkV0DrK8Vb'),
            ('Homem · inglês', 'elevenlabs:wBXNqKUATyqu0RtYt25i'),
        ))

    def test_gpt_image_response_is_saved_from_base64(self):
        from app.services import image_generation
        generated = Mock(return_value=SimpleNamespace(data=[SimpleNamespace(
            b64_json=base64.b64encode(b'image bytes' * 128).decode(),
        )]))
        client = SimpleNamespace(images=SimpleNamespace(generate=generated))
        module = ModuleType('openai')
        module.OpenAI = lambda **ignored: client
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(sys.modules, {'openai': module}), \
             patch.object(image_generation.config, 'image_generation', {
                 'openai_api_key': 'test', 'dalle_model': 'gpt-image-1'
             }), patch.object(image_generation.config, 'app', {}), patch.object(image_generation.config, 'llm', {}):
            result = image_generation.ImageGenerationService('dalle').generate_image(
                'uma imagem', 'scene-0', tmp, quality='standard', size='1024x1024'
            )
            self.assertEqual(Path(result).read_bytes(), b'image bytes' * 128)
            self.assertEqual(generated.call_args.kwargs['quality'], 'medium')

    def test_claude_client_omits_empty_base_url(self):
        from app.services.script_generator import ScriptGeneratorService
        created = []

        class FakeAnthropic:
            def __init__(self, **kwargs):
                created.append(kwargs)
                self.messages = SimpleNamespace(create=lambda **ignored: SimpleNamespace(
                    content=[SimpleNamespace(text='{}')],
                    usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                ))

        module = ModuleType('anthropic')
        module.Anthropic = FakeAnthropic
        with patch.dict(sys.modules, {'anthropic': module}):
            ScriptGeneratorService()._generate_claude('teste', {'api_key': 'test', 'model': 'claude-sonnet-4-6'})
        self.assertEqual(created, [{'api_key': 'test'}])

    def test_provider_connection_error_names_provider_and_configuration(self):
        from app.services.provider_errors import explain_generation_error
        message = explain_generation_error('claude', RuntimeError('Connection error'))
        self.assertIn('Claude', message)
        self.assertIn('conexão', message.lower())
        self.assertIn('Configurações', message)

    def test_retired_script_models_have_a_replacement_message(self):
        from app.services.provider_errors import model_status_message
        message = model_status_message('gemini', 'gemini-2.0-flash-exp')
        self.assertIn('descontinuado', message)
        self.assertIn('gemini-3.5-flash', message)

    def test_process_lease_prevents_second_worker(self):
        from app.services.studio_lease import acquire, release, is_locked
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'worker.lock'
            first = acquire(target)
            try:
                self.assertTrue(is_locked(target))
                with self.assertRaises(ValueError):
                    acquire(target)
            finally:
                release(first)
            self.assertFalse(is_locked(target))

    def test_queue_reserves_slot_before_thread_starts(self):
        from app.controllers.manager.memory_manager import InMemoryTaskManager
        manager = InMemoryTaskManager(1, 1)
        with patch('app.controllers.manager.base_manager.threading.Thread'):
            manager.add_task(lambda: None)
            manager.add_task(lambda: None)
        self.assertEqual(manager.current_tasks, 1)
        self.assertEqual(manager.queue_size(), 1)

    def test_disabled_llm_rejected_before_external_call(self):
        from app.services.script_generator import ScriptGeneratorService
        from app.models.schema import ScriptGenerationRequest
        generator = ScriptGeneratorService()
        generator.llm_configs = {'openai': {'api_key': 'test', 'enabled': False}}
        with patch.object(generator, '_generate_openai') as generate:
            with self.assertRaisesRegex(ValueError, 'desabilitado'):
                generator.generate_script(ScriptGenerationRequest(topic='Teste'))
            generate.assert_not_called()

    def test_artifacts_available_after_thumbnail_failure(self):
        from app.services import studio
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)), \
             patch.object(studio, 'validate_settings', return_value=[]), patch.object(studio, '_manager'):
            identifier = studio.submit(LongFormVideoParams(video_subject='Teste', structured_script=example_script()))
            folder = studio._folder(identifier)
            (folder / 'script.json').write_text('{}')
            record = studio.get_production(identifier)
            self.assertEqual(record['artifacts']['script'], str(folder / 'script.json'))
            studio._release(identifier)
    def test_drafts_persist_and_reject_path_traversal(self):
        from app.services import studio
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)):
            saved = studio.save_draft(example_script().model_dump())
            self.assertEqual(studio.list_drafts()[0]['script']['title'], 'Teste')
            with self.assertRaises(ValueError):
                studio.save_draft(example_script().model_dump(), '../outside')
            self.assertEqual(studio.save_draft(example_script().model_dump(), saved['id'])['id'], saved['id'])

    def test_queued_production_cannot_be_resumed_twice_and_survives_restart(self):
        from app.services import studio
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)), \
             patch.object(studio, 'validate_settings', return_value=[]), patch.object(studio, '_manager') as queue:
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script())
            identifier = studio.submit(params)
            with self.assertRaises(ValueError):
                studio.resume(identifier)
            self.assertEqual(queue.add_task.call_count, 1)
            studio._release(identifier)
            self.assertEqual(studio.get_production(identifier)['status'], 'interrupted')
            studio.resume(identifier)
            self.assertEqual(queue.add_task.call_count, 2)
            studio._release(identifier)

    def test_configuration_does_not_erase_or_return_secrets(self):
        from app.services import studio_settings as settings
        from app.config import config
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, 'config_file', str(Path(tmp) / 'config.toml')), \
             patch.object(config, '_cfg', {}), patch.object(config, 'llm', {}), \
             patch.object(config, 'image_generation', {}), patch.object(config, 'premium_tts', {}):
            settings.save_settings({'llm': {'openai': {'api_key': 'secret-test', 'model': 'test', 'enabled': True}}})
            settings.save_settings({'llm': {'openai': {'api_key': '', 'model': 'updated'}}})
            self.assertEqual(config.llm['openai']['api_key'], 'secret-test')
            self.assertTrue(settings.get_settings()['llm']['openai']['configured'])
            self.assertNotIn('secret-test', json.dumps(settings.get_settings()))
            with self.assertRaises(ValueError):
                settings.save_settings({'llm': {'openai': {'api_key': 'sk-...xyz'}}})

    def test_worker_failure_redacts_credentials(self):
        from app.services import studio
        from app.config import config
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)), \
             patch.object(studio, 'validate_settings', return_value=[]), patch.object(studio, '_manager'), \
             patch.dict(config.llm, {'openai': {'api_key': 'do-not-leak'}}), \
             patch('app.services.longform_pipeline.run', side_effect=RuntimeError('failed do-not-leak')):
            params = LongFormVideoParams(video_subject='Teste', structured_script=example_script())
            identifier = studio.submit(params)
            studio._run(identifier)
            record = studio.get_production(identifier)
            self.assertEqual(record['status'], 'failed')
            self.assertNotIn('do-not-leak', json.dumps(record))

if __name__ == '__main__':
    unittest.main()

