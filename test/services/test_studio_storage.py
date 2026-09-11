import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import studio_storage


class StudioStorageTests(unittest.TestCase):
    def test_write_json_uses_an_exclusive_temporary_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'production.json'
            original_replace = os.replace
            seen = []

            def capture(source, destination):
                seen.append(Path(source).name)
                return original_replace(source, destination)

            with patch.object(studio_storage.os, 'replace', side_effect=capture):
                studio_storage.write_json(target, {'status': 'running'})

            self.assertNotEqual(seen, ['production.tmp'])
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'status': 'running'})

    def test_write_json_retries_a_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'production.json'
            original_replace = os.replace
            attempts = 0

            def temporarily_locked(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(5, 'Acesso negado')
                return original_replace(source, destination)

            with patch.object(studio_storage.os, 'replace', side_effect=temporarily_locked), \
                 patch.object(studio_storage.time, 'sleep'):
                studio_storage.write_json(target, {'status': 'running'})

            self.assertEqual(attempts, 2)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'status': 'running'})
