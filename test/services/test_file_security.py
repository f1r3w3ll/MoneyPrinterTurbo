import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.utils import file_security


class TestResolvePathWithinDirectory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base_dir = self._tmp.name
        self.file_path = os.path.join(self.base_dir, "video.mp4")
        with open(self.file_path, "wb") as f:
            f.write(b"fake")

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_resolved_path_for_file_inside_directory(self):
        result = file_security.resolve_path_within_directory(
            self.base_dir, "video.mp4"
        )
        self.assertEqual(result, os.path.realpath(self.file_path))

    def test_accepts_absolute_path_inside_directory(self):
        result = file_security.resolve_path_within_directory(
            self.base_dir, self.file_path
        )
        self.assertEqual(result, os.path.realpath(self.file_path))

    def test_rejects_parent_directory_traversal(self):
        with self.assertRaises(ValueError):
            file_security.resolve_path_within_directory(
                self.base_dir, os.path.join("..", "outside.mp4")
            )

    def test_rejects_absolute_path_outside_directory(self):
        outside_dir = tempfile.mkdtemp()
        try:
            outside_file = os.path.join(outside_dir, "outside.mp4")
            with open(outside_file, "wb") as f:
                f.write(b"fake")
            with self.assertRaises(ValueError) as ctx:
                file_security.resolve_path_within_directory(
                    self.base_dir, outside_file
                )
            self.assertIn("outside the allowed directory", str(ctx.exception))
        finally:
            os.unlink(outside_file)
            os.rmdir(outside_dir)

    def test_rejects_empty_path(self):
        with self.assertRaises(ValueError) as ctx:
            file_security.resolve_path_within_directory(self.base_dir, "")
        self.assertIn("empty path", str(ctx.exception))

    def test_rejects_missing_file_by_default(self):
        with self.assertRaises(ValueError) as ctx:
            file_security.resolve_path_within_directory(self.base_dir, "missing.mp4")
        self.assertIn("file does not exist", str(ctx.exception))

    def test_allows_missing_file_when_require_file_is_false(self):
        result = file_security.resolve_path_within_directory(
            self.base_dir, "missing.mp4", require_file=False
        )
        self.assertEqual(
            result, os.path.realpath(os.path.join(self.base_dir, "missing.mp4"))
        )

    def test_rejects_symlink_pointing_outside(self):
        if os.name == "nt":
            self.skipTest("symlink creation may require elevated privileges on Windows")
        outside = tempfile.NamedTemporaryFile(delete=False)
        try:
            link = os.path.join(self.base_dir, "link.mp4")
            os.symlink(outside.name, link)
            with self.assertRaises(ValueError):
                file_security.resolve_path_within_directory(self.base_dir, "link.mp4")
        finally:
            outside.close()
            os.unlink(outside.name)


if __name__ == "__main__":
    unittest.main()
