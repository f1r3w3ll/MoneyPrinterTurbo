import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

from app.asgi import app
from app.models.exception import LLMError


class TestPingEndpoint(unittest.TestCase):
    def test_ping_returns_pong(self):
        client = TestClient(app)
        response = client.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), "pong")


class TestLLMEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_scripts_returns_generated_script(self):
        with patch(
            "app.services.llm.generate_script", return_value="hello script"
        ) as mock_generate:
            response = self.client.post(
                "/api/v1/scripts", json={"video_subject": "test"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["video_script"], "hello script"
        )
        mock_generate.assert_called_once()

    def test_scripts_returns_500_when_llm_fails(self):
        with patch(
            "app.services.llm.generate_script",
            side_effect=LLMError("api_key is not set"),
        ):
            response = self.client.post(
                "/api/v1/scripts", json={"video_subject": "test"}
            )
        self.assertEqual(response.status_code, 500)

    def test_scripts_returns_400_on_invalid_paragraph_number(self):
        response = self.client.post(
            "/api/v1/scripts", json={"video_subject": "test", "paragraph_number": 99}
        )
        self.assertEqual(response.status_code, 400)

    def test_terms_returns_generated_terms(self):
        with patch(
            "app.services.llm.generate_terms", return_value=["sky", "tree"]
        ):
            response = self.client.post(
                "/api/v1/terms",
                json={"video_subject": "test", "video_script": "a script"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["video_terms"], ["sky", "tree"])


if __name__ == "__main__":
    unittest.main()
