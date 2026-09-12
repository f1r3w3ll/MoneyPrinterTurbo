import ast
import json
from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).parent.parent.parent
WEBUI_MAIN = ROOT_DIR / "webui" / "Main.py"
I18N_DIR = ROOT_DIR / "webui" / "i18n"


class _TrKeyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.keys = set()

    def visit_Call(self, node):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "tr"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self.keys.add(node.args[0].value)
        self.generic_visit(node)


def _load_translation(locale):
    data = json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return data.get("Translation", {})


def _collect_static_tr_keys():
    tree = ast.parse(WEBUI_MAIN.read_text(encoding="utf-8"))
    visitor = _TrKeyVisitor()
    visitor.visit(tree)
    return visitor.keys


def _non_english_locales():
    return sorted(
        p.stem for p in I18N_DIR.glob("*.json") if p.stem != "en"
    )


class TestWebuiI18n(unittest.TestCase):
    def test_english_locale_covers_static_webui_labels(self):
        en_keys = set(_load_translation("en"))
        self.assertEqual(sorted(_collect_static_tr_keys() - en_keys), [])

    def test_every_locale_covers_english_locale(self):
        en_keys = set(_load_translation("en"))
        for locale in _non_english_locales():
            with self.subTest(locale=locale):
                locale_keys = set(_load_translation(locale))
                self.assertEqual(sorted(en_keys - locale_keys), [])

    def test_every_locale_covers_static_webui_labels(self):
        static_keys = _collect_static_tr_keys()
        for locale in _non_english_locales():
            with self.subTest(locale=locale):
                locale_keys = set(_load_translation(locale))
                self.assertEqual(sorted(static_keys - locale_keys), [])

    def test_script_language_options_include_russian(self):
        tree = ast.parse(WEBUI_MAIN.read_text(encoding="utf-8"))
        support_locales = None

        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "support_locales"
                for target in node.targets
            ):
                support_locales = ast.literal_eval(node.value)
                break

        self.assertIsNotNone(support_locales)
        self.assertIn("ru-RU", support_locales)
