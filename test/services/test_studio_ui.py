import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch, Mock
from streamlit.testing.v1 import AppTest
import numpy  # Keep extension modules outside the temporary service registry.
from webui import studio


class StudioUITest(unittest.TestCase):
    def test_publication_uses_editorial_title_and_extracts_description_from_json(self):
        record = {
            'title': 'Título de reserva',
            'params': {
                'thumbnail_text': 'TEXTO CURTO',
                'structured_script': {
                    'title': 'Título do roteiro',
                    'metadata': {'editorial': {'selected_package': {'title': 'Título editorial completo'}}},
                },
            },
        }
        self.assertEqual(studio._publication_title(record), 'Título editorial completo')
        raw = '{"description": "A clean YouTube description.", "tags": ["AI"]}'
        self.assertEqual(studio._publication_description(raw), 'A clean YouTube description.')
        self.assertEqual(studio._publication_language({'metadata': {'editorial': {'channel': {'language': 'en-US'}}}}), 'en-US')
        self.assertEqual(studio._youtube_title('A title that should stay intact'), 'A title that should stay intact')
        self.assertLessEqual(len(studio._youtube_title('A very long title ' * 20)), 100)

    def test_publication_description_renders_the_fixed_editorial_sequence(self):
        raw = '''{
          "summary": "A concise video summary.",
          "chapters": [{"time": "00:00", "title": "The beginning"}],
          "takeaways": ["A practical idea"],
          "sources": ["Official technical documentation"],
          "cta": "Subscribe for the next episode.",
          "hashtags": ["#Technology", "#Science"],
          "tags": ["technology explained", "data centers"]
        }'''
        description, tags = studio._publication_content(raw)
        self.assertEqual(tags, ['technology explained', 'data centers'])
        self.assertLess(description.index('VIDEO SUMMARY'), description.index('CHAPTERS'))
        self.assertLess(description.index('CHAPTERS'), description.index('KEY TAKEAWAYS'))
        self.assertLess(description.index('KEY TAKEAWAYS'), description.index('SOURCES & NOTES'))
        self.assertLess(description.index('SOURCES & NOTES'), description.index('Subscribe for the next episode.'))
        self.assertTrue(description.endswith('#Technology #Science'))

    def test_publication_allows_completed_video_regardless_of_duration(self):
        short_record = {
            'title': 'Vídeo curto',
            'artifacts': {'duration_seconds': 52.09},
            'params': {'structured_script': {'metadata': {'target_duration_seconds': 1200}}},
        }
        valid_record = {
            'title': 'Vídeo válido',
            'artifacts': {'duration_seconds': 980.96},
            'params': {'structured_script': {'metadata': {'target_duration_seconds': 1200}}},
        }
        self.assertIsNone(studio._publication_duration_error(short_record))
        self.assertIsNone(studio._publication_duration_error(valid_record))

    def test_publication_label_includes_duration_file_size_and_creation_date(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'video.mp4'
            video.write_bytes(b'x' * 2 * 1024 * 1024)
            created_at = datetime(2026, 9, 9, 15, 11).timestamp()
            record = {
                'title': 'Produção identificável',
                'created_at': created_at,
                'artifacts': {'duration_seconds': 980.96, 'video': str(video)},
            }
            label = studio._publication_label(record)
            self.assertIn('Produção identificável', label)
            self.assertIn('16.3 min', label)
            self.assertIn('2.0 MB', label)
            self.assertIn(datetime.fromtimestamp(created_at).strftime('%d/%m/%Y %H:%M'), label)

    def test_elapsed_production_time_uses_start_timestamp(self):
        record = {'created_at': 100.0, 'started_at': 120.0}
        self.assertEqual(studio._production_elapsed_label(record, now=185.0), '01:05')

    def test_production_controls_appear_only_after_a_script_is_ready(self):
        backend = ModuleType('app.services.studio')
        backend.list_drafts = Mock(return_value=[])
        backend.list_productions = Mock(return_value=[])
        settings = ModuleType('app.services.studio_settings')
        settings.get_settings = Mock(return_value={'llm': {}, 'image_generation': {}, 'premium_tts': {}})
        with patch.dict(sys.modules, {'app.services.studio': backend, 'app.services.studio_settings': settings}):
            app = AppTest.from_string('from webui.studio import render\nrender()', default_timeout=40).run()
            self.assertNotIn('produce', [button.key for button in app.button])
            self.assertTrue(any('Salve um roteiro' in item.value for item in app.info))
            app.button(key='new_script').click().run()
            self.assertIn('produce', [button.key for button in app.button])
            self.assertEqual(app.selectbox(key='output_aspect').value, 'Paisagem · 16:9')

    def test_editor_saved_and_submission_not_repeated_on_rerun(self):
        backend = ModuleType('app.services.studio')
        backend.list_drafts = Mock(return_value=[])
        backend.list_productions = Mock(return_value=[])
        backend.validate_settings = Mock(return_value=[])
        backend.submit = Mock(return_value='task-1')
        backend.get_production = Mock(return_value={
            'id': 'task-1', 'title': 'Meu documentário', 'status': 'running',
            'phase': 'images', 'progress': 44, 'error': None,
        })
        backend.save_draft = Mock(side_effect=lambda script, draft_id=None: {'id': 'draft-1', 'script': script})
        settings = ModuleType('app.services.studio_settings')
        settings.get_settings = Mock(return_value={'llm': {}, 'image_generation': {}, 'premium_tts': {}})
        with patch.dict(sys.modules, {'app.services.studio': backend, 'app.services.studio_settings': settings}):
            app = AppTest.from_string('from webui.studio import render\nrender()', default_timeout=40).run()
            self.assertFalse(app.exception)

            app.button(key='new_script').click().run()
            app.text_input(key='script_title_1').set_value('Meu documentário')
            app.text_area(key='narration_1_0').set_value('Uma narração editada e preservada.')
            app.button(key='FormSubmitter:editor_1-Salvar roteiro').click().run()
            self.assertEqual(backend.save_draft.call_args.args[0]['title'], 'Meu documentário')
            self.assertEqual(backend.save_draft.call_args.args[0]['scenes'][0]['narration'], 'Uma narração editada e preservada.')
            app.button(key='FormSubmitter:editor_1-Salvar e adicionar cena').click().run()
            self.assertEqual(len(app.session_state.studio_script['scenes']), 31)
            self.assertEqual(app.session_state.studio_script['scenes'][0]['narration'], 'Uma narração editada e preservada.')
            app.button(key='FormSubmitter:editor_2-Salvar e remover última cena').click().run()
            self.assertEqual(len(app.session_state.studio_script['scenes']), 30)
            app.selectbox(key='output_aspect').set_value('Paisagem · 16:9')
            app.checkbox(key='output_subtitles').check()
            app.selectbox(key='subtitle_position').set_value('Centro')
            app.color_picker(key='subtitle_foreground').set_value('#112233')
            app.slider(key='subtitle_font_size').set_value(72)
            app.color_picker(key='subtitle_stroke_color').set_value('#445566')
            app.slider(key='subtitle_stroke_width').set_value(3.0)
            app.checkbox(key='subtitle_background').check()
            app.color_picker(key='subtitle_background_color').set_value('#778899')
            app.text_input(key='output_thumbnail_text').set_value('CAPA')
            app.selectbox(key='output_thumbnail_style').set_value('template')
            app.selectbox(key='output_quality').set_value('hd')
            app.selectbox(key='output_size').set_value('1024x1792')
            app.button(key='produce').click().run()
            self.assertEqual(backend.submit.call_count, 1)
            backend.get_production.assert_called_with('task-1')
            self.assertTrue(any(item.value == 44 for item in app.get('progress')))
            params = backend.submit.call_args.args[0]
            self.assertEqual(params.video_aspect.value, '16:9')
            self.assertTrue(params.subtitle_enabled)
            self.assertEqual(params.subtitle_position, 'center')
            self.assertEqual(params.text_fore_color, '#112233')
            self.assertEqual(params.font_size, 72)
            self.assertEqual(params.stroke_color, '#445566')
            self.assertEqual(params.stroke_width, 3.0)
            self.assertEqual(params.text_background_color, '#778899')
            self.assertEqual(params.thumbnail_text, 'CAPA')
            self.assertEqual(params.thumbnail_style, 'template')
            self.assertEqual(params.image_quality, 'hd')
            self.assertEqual(params.image_size, '1024x1792')
            app.run()
            self.assertEqual(backend.submit.call_count, 1)
            self.assertFalse(app.exception)

    def test_invalid_settings_prevent_job_and_failed_job_can_resume(self):
        backend = ModuleType('app.services.studio')
        backend.list_drafts = Mock(return_value=[])
        backend.list_productions = Mock(return_value=[{'id': 'failed-1', 'title': 'Falhou', 'status': 'failed', 'phase': 'images', 'error': 'Sem conexão'}])
        backend.validate_settings = Mock(return_value=['Configure a chave de imagens.'])
        backend.submit = Mock()
        backend.resume = Mock()
        settings = ModuleType('app.services.studio_settings')
        settings.get_settings = Mock(return_value={'llm': {}, 'image_generation': {}, 'premium_tts': {}})
        with patch.dict(sys.modules, {'app.services.studio': backend, 'app.services.studio_settings': settings}):
            app = AppTest.from_string('from webui.studio import render\nrender()', default_timeout=40).run()
            app.button(key='new_script').click().run()
            app.button(key='produce').click().run()
            backend.submit.assert_not_called()
            self.assertTrue(any('Configure a chave' in item.value for item in app.error))
            app.button(key='resume_failed-1').click().run()
            backend.resume.assert_called_once_with('failed-1')
            self.assertFalse(app.exception)

if __name__ == '__main__':
    unittest.main()
