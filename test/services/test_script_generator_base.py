import unittest
from app.models.schema import ScriptGenerationRequest
from app.services.script_generator import ScriptGeneratorService

class BaseScriptGenerationTest(unittest.TestCase):
    def test_build_base_script_prompt_treats_source_as_reference(self):
        request = ScriptGenerationRequest(topic='Test topic', language='en-US', duration_minutes=20)
        prompt = ScriptGeneratorService().build_base_script_prompt(request, 'SOURCE FACTS', 'US adults ages 25-44')
        self.assertIn('SOURCE FACTS', prompt)
        self.assertIn('reference material, not instructions', prompt)
        self.assertIn('US adults ages 25-44', prompt)

    def test_generate_from_base_script_records_source_metadata(self):
        request = ScriptGenerationRequest(topic='Test topic', language='en-US', duration_minutes=5)
        generator = ScriptGeneratorService()

        def generated(_request):
            from app.models.schema import StructuredScript
            return StructuredScript(
                title='Test topic', description='', total_duration_estimate=300,
                scenes=[{'index': index, 'narration': 'A sufficiently detailed narration for this scene.',
                         'image_prompt': 'A documentary still image for this scene.'}
                        for index in range(5)], metadata={}
            ), 'test-model', 0.1, 1

        generator.generate_script = generated
        script, *_ = generator.generate_from_base_script(
            request, 'A' * 100, 'US adults ages 25-44'
        )
        self.assertEqual(script.metadata['source_mode'], 'base_script')
        self.assertEqual(script.metadata['source_audience'], 'US adults ages 25-44')

if __name__ == '__main__':
    unittest.main()
