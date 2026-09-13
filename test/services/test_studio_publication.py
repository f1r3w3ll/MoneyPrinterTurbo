import unittest

from webui.studio import _publication_audience


class PublicationAudienceTest(unittest.TestCase):
    def test_prefers_source_audience_and_falls_back_to_editorial_audience(self):
        self.assertEqual(
            _publication_audience({'metadata': {'source_audience': 'US tech viewers', 'editorial': {'audience': 'Other'}}}),
            'US tech viewers',
        )
        self.assertEqual(
            _publication_audience({'metadata': {'editorial': {'audience': 'US viewers'}}}),
            'US viewers',
        )


if __name__ == '__main__':
    unittest.main()
