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
    def test_channels_keep_independent_profiles_and_active_channel(self):
        from app.services import editorial
        with tempfile.TemporaryDirectory() as tmp, patch.object(editorial, 'ROOT', Path(tmp)):
            first = editorial.get_channel_profile()
            second = editorial.create_channel({'name': 'Canal Atlas', 'niche': 'História'})
            editorial.set_active_channel(second['id'])
            editorial.save_channel_profile({'name': 'Canal Atlas', 'niche': 'História e cultura'})

            self.assertEqual(first['name'], 'Fio da Ciência')
            self.assertEqual(first['language'], 'en-US')
            self.assertEqual(editorial.get_channel_profile()['niche'], 'História e cultura')
            self.assertEqual(editorial.get_channel_profile('fio-da-ciencia')['niche'], 'Science and technology explained')
            self.assertEqual(len(editorial.list_channels()), 2)

    def test_channel_profile_persists_and_packaging_keeps_the_promise(self):
        from app.services import editorial
        with tempfile.TemporaryDirectory() as tmp, patch.object(editorial, 'ROOT', Path(tmp)):
            saved = editorial.save_channel_profile({
                'name': 'Canal Atlas', 'niche': 'História da tecnologia',
                'audience': 'Curiosos adultos', 'promise': 'Explicar as forças por trás da tecnologia',
            })
            self.assertEqual(editorial.get_channel_profile()['name'], 'Canal Atlas')
            self.assertEqual(saved['niche'], 'História da tecnologia')
            options = editorial.packaging_options({
                'topic': 'A guerra dos navegadores',
                'central_question': 'Como um navegador mudou a internet?',
                'thesis': 'A disputa definiu a web moderna.',
                'promise': 'Entender por que essa batalha ainda afeta você.',
            })
            self.assertEqual(len(options), 3)
            self.assertTrue(all(option['thumbnail_text'] for option in options))
            self.assertTrue(all(option['promise'] == 'Entender por que essa batalha ainda afeta você.' for option in options))

    def test_ai_brief_generation_normalizes_editable_fields(self):
        from app.services import editorial

        generated = json.dumps({
            'central_question': 'Por que a disputa mudou a internet?',
            'thesis': 'A rivalidade definiu padrões que ainda usamos.',
            'promise': 'Entender como uma disputa comercial moldou sua navegação.',
            'goal': 'Descoberta',
            'sources': 'Buscar documentos, reportagens e fontes primárias.',
        })
        with patch('app.services.script_generator.ScriptGeneratorService.generate_editorial_json', return_value=generated) as generate:
            brief = editorial.generate_brief(
                'A guerra dos navegadores',
                {'niche': 'História da tecnologia', 'audience': 'Curiosos adultos', 'promise': 'Explicar as forças por trás da tecnologia'},
                'openai',
            )

        self.assertEqual(brief['topic'], 'A guerra dos navegadores')
        self.assertEqual(brief['central_question'], 'Por que a disputa mudou a internet?')
        self.assertEqual(brief['goal'], 'Descoberta')
        self.assertIn('A guerra dos navegadores', generate.call_args.args[1])

    def test_english_channel_gets_english_packaging_options(self):
        from app.services import editorial
        options = editorial.packaging_options({
            'topic': 'The hidden infrastructure behind AI',
            'central_question': 'What does AI physically cost America?',
            'thesis': 'AI depends on concentrated industrial infrastructure.',
            'promise': 'Understand the systems behind every AI prompt.',
        }, language='en-US')

        self.assertEqual(options[0]['angle'], 'Central question')
        self.assertIn('What really happened', options[1]['title'])
        self.assertIn('AI still affects you', options[2]['title'])
        self.assertIn('Visual contrast', options[0]['visual_concept'])

    def test_packaging_titles_keep_a_readable_youtube_length(self):
        from app.services import editorial
        options = editorial.packaging_options({
            'topic': 'The hidden infrastructure behind artificial intelligence and the data center boom reshaping American communities',
            'central_question': 'How is the hidden infrastructure behind artificial intelligence and the data center boom reshaping American communities?',
            'thesis': 'AI depends on concentrated industrial infrastructure.',
            'promise': 'Understand the systems behind every AI prompt.',
        }, language='en-US')

        self.assertTrue(all(len(option['title']) <= 70 for option in options))
        self.assertTrue(all(not option['title'].endswith(' ') for option in options))

    def test_editorial_context_is_present_in_script_prompt_and_metadata(self):
        from app.models.schema import ScriptGenerationRequest
        from app.services.script_generator import ScriptGeneratorService

        request = ScriptGenerationRequest(
            topic='A guerra dos navegadores',
            editorial_context={
                'brief': {'promise': 'Entender por que essa batalha ainda afeta você.'},
                'selected_package': {'title': 'Como a guerra dos navegadores mudou a internet'},
            },
        )
        generator = ScriptGeneratorService()
        prompt = generator._build_prompt(request)
        script = generator._parse_script_json(json.dumps({
            'title': 'Título', 'description': '', 'total_duration_estimate': 900,
            'scenes': [dict(index=index, narration='Uma narração completa para esta cena.', image_prompt='Imagem documental detalhada') for index in range(5)],
            'metadata': {'editorial': {'hook': 'Uma disputa aparentemente pequena mudou a web.'}},
        }), request)

        self.assertIn('meaningful change of pace', prompt)
        self.assertIn('Como a guerra dos navegadores mudou a internet', prompt)
        self.assertEqual(script.metadata['editorial']['brief']['promise'], 'Entender por que essa batalha ainda afeta você.')
        self.assertEqual(script.metadata['editorial']['hook'], 'Uma disputa aparentemente pequena mudou a web.')

    def test_script_generation_turns_duration_into_narration_budget(self):
        from app.models.schema import ScriptGenerationRequest
        from app.services.script_generator import ScriptGeneratorService

        request = ScriptGenerationRequest(
            topic='Hidden infrastructure behind AI',
            duration_minutes=20,
            language='en-US',
        )
        generator = ScriptGeneratorService()
        prompt = generator._build_prompt(request)
        script = generator._parse_script_json(json.dumps({
            'title': 'Title', 'description': '', 'total_duration_estimate': 1200,
            'scenes': [dict(index=index, narration='A complete narration for this scene.', image_prompt='Detailed documentary image') for index in range(5)],
        }), request)

        self.assertIn('Narration budget', prompt)
        self.assertIn('15,600', prompt)
        self.assertEqual(script.metadata['script_language'], 'en-US')
        self.assertEqual(script.metadata['target_duration_seconds'], 1200)

    def test_english_script_normalizes_a_portuguese_subscribe_cta(self):
        from app.models.schema import ScriptGenerationRequest
        from app.services.script_generator import ScriptGeneratorService

        script = ScriptGeneratorService()._parse_script_json(json.dumps({
            'title': 'Title', 'description': '', 'total_duration_estimate': 900,
            'scenes': [dict(index=index, narration='Fio da Ciência - inscreva-se' if index == 4 else 'Complete English narration for this scene.', image_prompt='Detailed documentary image', narrative_role='CTA' if index == 4 else 'context') for index in range(5)],
        }), ScriptGenerationRequest(topic='AI', language='en-US'))

        self.assertIn('Subscribe', script.scenes[4].narration)
        self.assertNotIn('inscreva-se', script.scenes[4].narration.lower())

    def test_longform_script_is_generated_in_bounded_scene_batches(self):
        from app.models.schema import ScriptGenerationRequest
        from app.services.script_generator import ScriptGeneratorService

        generator = ScriptGeneratorService()
        generator.llm_configs = {'openai': {'api_key': 'test', 'enabled': True}}
        response = json.dumps({
            'title': 'AI infrastructure', 'description': 'Description', 'total_duration_estimate': 300,
            'scenes': [dict(index=index, narration='A complete scene narration with enough detail for testing.', image_prompt='Detailed documentary image') for index in range(12)],
        })
        with patch.object(generator, '_generate_openai', return_value=(response, 'gpt-4o', 100)) as generate:
            script, model, _, tokens = generator.generate_script(
                ScriptGenerationRequest(topic='AI infrastructure', duration_minutes=20, language='en-US')
            )

        self.assertEqual(generate.call_count, 4)
        self.assertEqual(len(script.scenes), 48)
        self.assertEqual(script.metadata['target_scene_count'], 48)
        self.assertEqual(model, 'gpt-4o')
        self.assertEqual(tokens, 400)

    def test_longform_duration_margin_accepts_fifteen_minutes_for_a_twenty_minute_target(self):
        from webui.studio import _duration_is_on_target

        self.assertTrue(_duration_is_on_target(15.7 * 60, 20 * 60))
        self.assertFalse(_duration_is_on_target(14.9 * 60, 20 * 60))

    def test_duration_correction_is_limited_and_preserves_editorial_metadata(self):
        from app.models.schema import ScriptGenerationRequest
        from app.services.script_generator import ScriptGeneratorService

        generator = ScriptGeneratorService()
        original = generator._parse_script_json(json.dumps({
            'title': 'AI infrastructure', 'description': '', 'total_duration_estimate': 1200,
            'scenes': [dict(index=index, narration='Short but complete narration for this scene.', image_prompt='Detailed documentary image') for index in range(5)],
            'metadata': {'editorial': {'promise': 'Explain the hidden systems.'}},
        }), ScriptGenerationRequest(topic='AI infrastructure', duration_minutes=20, language='en-US'))
        corrected_json = json.dumps({
            'title': original.title, 'description': '', 'total_duration_estimate': 1200,
            'scenes': [dict(index=index, narration='Expanded narration that keeps the original point while providing substantially more useful context for the viewer.', image_prompt='Changed image prompt', duration_seconds=120) for index in range(5)],
        })

        with patch.object(generator, 'generate_editorial_json', return_value=corrected_json) as generate:
            corrected = generator.correct_script_duration(original, 'openai')

        self.assertIn('Rewrite only the narration', generate.call_args.args[1])
        self.assertEqual(corrected.metadata['duration_correction_attempts'], 1)
        self.assertEqual(corrected.metadata['editorial']['promise'], 'Explain the hidden systems.')
        self.assertTrue(all(scene.duration_seconds is None for scene in corrected.scenes))
        self.assertTrue(all(scene.image_prompt == 'Detailed documentary image' for scene in corrected.scenes))
        with self.assertRaisesRegex(ValueError, 'já foi usada'):
            generator.correct_script_duration(corrected, 'openai')

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

    def test_openai_script_generation_reserves_longform_output_capacity(self):
        from app.services.script_generator import ScriptGeneratorService
        calls = []

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))],
                    usage=None,
                )

        module = ModuleType('openai')
        module.OpenAI = FakeOpenAI
        with patch.dict(sys.modules, {'openai': module}):
            ScriptGeneratorService()._generate_openai('teste', {'api_key': 'test', 'model': 'gpt-4o'})

        self.assertEqual(calls[0]['max_tokens'], 12000)

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
            script = example_script().model_dump()
            script['metadata'] = {'editorial': {'selected_package': {'title': 'Título escolhido'}}}
            saved = studio.save_draft(script)
            self.assertEqual(studio.list_drafts()[0]['script']['title'], 'Teste')
            self.assertEqual(studio.list_drafts()[0]['script']['metadata']['editorial']['selected_package']['title'], 'Título escolhido')
            with self.assertRaises(ValueError):
                studio.save_draft(script, '../outside')
            self.assertEqual(studio.save_draft(script, saved['id'])['id'], saved['id'])

    def test_delete_production_removes_its_entire_project_folder(self):
        from app.services import studio
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)), \
             patch.object(studio, 'validate_settings', return_value=[]), patch.object(studio, '_manager'):
            identifier = studio.submit(LongFormVideoParams(video_subject='Teste', structured_script=example_script()))
            folder = studio._folder(identifier)
            (folder / 'final.mp4').write_bytes(b'video')
            studio._release(identifier)
            studio.delete_production(identifier)
            self.assertFalse(folder.exists())

    def test_delete_production_rejects_a_queued_project(self):
        from app.services import studio
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'ROOT', Path(tmp)), \
             patch.object(studio, 'validate_settings', return_value=[]), patch.object(studio, '_manager'):
            identifier = studio.submit(LongFormVideoParams(video_subject='Teste', structured_script=example_script()))
            with self.assertRaises(ValueError):
                studio.delete_production(identifier)
            self.assertTrue(studio._folder(identifier).exists())
            studio._release(identifier)

    def test_woopsocial_accepts_a_top_level_accounts_list(self):
        from app.services import woopsocial
        response = Mock()
        response.json.return_value = [
            {'id': 'youtube-1', 'platform': 'YOUTUBE', 'name': 'Canal'},
            {'id': 'instagram-1', 'platform': 'INSTAGRAM', 'name': 'Outro'},
        ]
        with patch('app.services.woopsocial.requests.get', return_value=response), \
             patch('app.services.woopsocial._headers', return_value={}):
            self.assertEqual(woopsocial.youtube_accounts(), [{'id': 'youtube-1', 'platform': 'YOUTUBE', 'name': 'Canal'}])

    def test_woopsocial_uses_username_as_channel_label(self):
        from app.services import woopsocial
        self.assertEqual(woopsocial.account_label({'id': '171275273835118592', 'username': 'No One Wrote It Down'}), 'No One Wrote It Down')

    def test_woopsocial_uploads_video_to_project_and_posts_youtube_payload(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            upload = Mock(); upload.json.return_value = {'mediaId': 'media-1'}
            validation = Mock(); validation.json.return_value = {'isValid': True, 'errors': []}
            posted = Mock(); posted.json.return_value = {'id': 'post-1'}
            with patch('app.services.woopsocial.requests.post', side_effect=[upload, validation, posted]) as request, \
                 patch('app.services.woopsocial._headers', return_value={'Authorization': 'Bearer test'}):
                self.assertEqual(woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private'), {'id': 'post-1'})
            self.assertEqual(request.call_args_list[0].kwargs['params'], {'projectId': 'project-1'})
            payload = request.call_args_list[1].kwargs['json']
            self.assertEqual(payload['schedule'], {'type': 'PUBLISH_NOW'})
            self.assertEqual(payload['socialAccounts'][0], {'platform': 'YOUTUBE', 'socialAccountId': 'account-1', 'title': 'Title', 'privacy': 'private'})
            self.assertEqual(request.call_args_list[1].args[0], f'{woopsocial.BASE_URL}/posts/validate')
            self.assertEqual(request.call_args_list[2].args[0], f'{woopsocial.BASE_URL}/posts')

    def test_woopsocial_uses_upload_session_for_larger_videos(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            session = Mock(); session.json.return_value = {
                'uploadSessionId': 'session-1', 'partSizeInBytes': 10, 'partCount': 1,
                'parts': [{'partNumber': 1, 'uploadUrl': 'https://upload.example/part-1'}],
            }
            completed = Mock(); completed.json.return_value = {'uploadSessionId': 'session-1', 'status': 'UPLOADED'}
            ready = Mock(); ready.json.return_value = {'uploadSessionId': 'session-1', 'status': 'READY', 'mediaId': 'media-1'}
            validation = Mock(); validation.json.return_value = {'isValid': True, 'errors': []}
            posted = Mock(); posted.json.return_value = {'id': 'post-1'}
            uploaded_part = Mock()
            with patch('app.services.woopsocial.requests.post', side_effect=[session, completed, validation, posted]) as post, \
                 patch('app.services.woopsocial.requests.put', return_value=uploaded_part) as put, \
                 patch('app.services.woopsocial.requests.get', return_value=ready), \
                 patch('app.services.woopsocial._headers', return_value={'Authorization': 'Bearer test'}), \
                 patch.object(woopsocial, 'CHUNKED_UPLOAD_THRESHOLD_BYTES', 1):
                self.assertEqual(woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private'), {'id': 'post-1'})
            self.assertEqual(post.call_args_list[0].args[0], f'{woopsocial.BASE_URL}/media/upload-sessions')
            self.assertEqual(post.call_args_list[0].kwargs['json'], {'projectId': 'project-1', 'fileSizeInBytes': 5})
            put.assert_called_once_with('https://upload.example/part-1', data=b'video', timeout=600)
            self.assertEqual(post.call_args_list[1].args[0], f'{woopsocial.BASE_URL}/media/upload-sessions/session-1/complete')
            self.assertEqual(post.call_args_list[2].args[0], f'{woopsocial.BASE_URL}/posts/validate')

    def test_woopsocial_stops_when_upload_response_has_no_media_id(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            upload = Mock(); upload.json.return_value = {'media': {}}
            with patch('app.services.woopsocial.requests.post', return_value=upload) as request, \
                 patch('app.services.woopsocial._headers', return_value={}):
                with self.assertRaisesRegex(ValueError, 'identificador da mídia'):
                    woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private')
            self.assertEqual(request.call_count, 1)

    def test_woopsocial_rejects_an_overlong_youtube_title_before_upload(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            with patch('app.services.woopsocial.requests.post') as request:
                with self.assertRaisesRegex(ValueError, '100 caracteres'):
                    woopsocial.publish(video, 'project-1', 'account-1', 'A' * 101, 'Description', 'private')
            request.assert_not_called()

    def test_woopsocial_sends_youtube_tags(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            upload = Mock(); upload.json.return_value = {'id': 'media-1'}
            validation = Mock(); validation.json.return_value = {'isValid': True, 'errors': []}
            posted = Mock(); posted.json.return_value = {'id': 'post-1'}
            with patch('app.services.woopsocial.requests.post', side_effect=[upload, validation, posted]) as request, \
                 patch('app.services.woopsocial._headers', return_value={}):
                woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private', tags=['science', 'technology'])
            self.assertEqual(request.call_args_list[1].kwargs['json']['socialAccounts'][0]['tags'], ['science', 'technology'])

    def test_woopsocial_reports_validation_errors_without_creating_post(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            upload = Mock(); upload.json.return_value = {'id': 'media-1'}
            validation = Mock(); validation.json.return_value = {'isValid': False, 'errors': [{'message': 'Invalid YouTube setting'}]}
            with patch('app.services.woopsocial.requests.post', side_effect=[upload, validation]) as request, \
                 patch('app.services.woopsocial._headers', return_value={}):
                with self.assertRaisesRegex(ValueError, 'Invalid YouTube setting'):
                    woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private')
            self.assertEqual(request.call_count, 2)

    def test_woopsocial_exposes_api_validation_error_details(self):
        from app.services import woopsocial
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'video.mp4'
            video.write_bytes(b'video')
            upload = Mock(); upload.json.return_value = {'id': 'media-1'}
            validation = Mock(); validation.status_code = 400; validation.text = '{"error_message":"specific API rule"}'
            validation.json.return_value = {'error_message': 'specific API rule'}
            validation.raise_for_status.side_effect = Exception('HTTP 400')
            with patch('app.services.woopsocial.requests.post', side_effect=[upload, validation]), \
                 patch('app.services.woopsocial._headers', return_value={}):
                with self.assertRaisesRegex(ValueError, 'specific API rule'):
                    woopsocial.publish(video, 'project-1', 'account-1', 'Title', 'Description', 'private')

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

