# CTA visual e logo por canal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Permitir logo por canal e CTA final por texto, imagem ou vídeo em produções do Estúdio.

**Architecture:** `editorial.py` salva os ativos por canal. `studio.py` permite escolha do CTA e congela os arquivos no projeto. `longform_media.py` acrescenta a endcard ao MP4 final por Pillow e MoviePy.

**Tech Stack:** Python 3.11, Streamlit, Pydantic, Pillow, MoviePy, unittest.

---

### Task 1: Perfil e ativos do canal

**Files:**
- Modify: `app/services/editorial.py`
- Test: `test/services/test_studio.py`

- [x] **Step 1: Write the failing test**

```python
def test_channel_profile_saves_logo_and_cta_asset(self):
    from app.services import editorial
    with tempfile.TemporaryDirectory() as tmp, patch.object(editorial, 'ROOT', Path(tmp)):
        logo = editorial.save_channel_asset('canal-atlas', 'logo.png', b'png', 'logo')
        cta = editorial.save_channel_asset('canal-atlas', 'cta.jpg', b'jpg', 'cta')
        saved = editorial.save_channel_profile({'name': 'Canal Atlas', 'niche': 'Ciência',
            'logo_path': str(logo), 'cta_mode': 'image', 'cta_asset_path': str(cta)})
        self.assertEqual(saved['cta_mode'], 'image')
        self.assertTrue(Path(saved['logo_path']).is_file())
        self.assertTrue(Path(saved['cta_asset_path']).is_file())
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_channel_profile_saves_logo_and_cta_asset`

Expected: FAIL because `save_channel_asset` does not exist.

- [x] **Step 3: Write minimal implementation**

Add `logo_path`, `cta_mode`, and `cta_asset_path` to profile defaults. Add `save_channel_asset(channel_id, filename, content, kind)`, writing `logo` or `cta` into `storage/studio/channel_assets/<channel>/` with the supplied suffix. Normalize mode to `text`, `image`, or `video`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_channel_profile_saves_logo_and_cta_asset`

Expected: PASS.

### Task 2: Produção preserva ativos

**Files:**
- Modify: `app/models/schema.py`
- Modify: `app/services/studio.py`
- Modify: `app/services/studio_settings.py`
- Test: `test/services/test_studio.py`

- [x] **Step 1: Write the failing test**

```python
def test_production_copies_configured_cta_assets(self):
    logo = Path(tmp) / 'logo.png'; logo.write_bytes(b'logo')
    params = LongFormVideoParams(video_subject='Teste', structured_script=example_script(),
        use_structured_script=True, cta_mode='text', cta_text='Subscribe', channel_logo_path=str(logo))
    identifier = studio.submit(params)
    self.assertIn(identifier, studio.get_production(identifier)['params']['channel_logo_path'])
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_production_copies_configured_cta_assets`

Expected: FAIL because CTA fields and project asset copying do not exist.

- [x] **Step 3: Write minimal implementation**

Add `cta_mode`, `cta_text`, `cta_asset_path`, and `channel_logo_path` to `LongFormVideoParams`. In `studio.submit`, copy valid files to `production/assets/` before serializing parameters. Validate required image/video assets and allow text without a logo.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_production_copies_configured_cta_assets`

Expected: PASS.

### Task 3: Endcard visual

**Files:**
- Modify: `app/services/longform_media.py`
- Modify: `app/services/longform_pipeline.py`
- Test: `test/services/test_studio_render.py`

- [x] **Step 1: Write the failing tests**

```python
def test_text_cta_endcard_contains_logo_and_last_five_seconds(self):
    # Append a text CTA with an asymmetric logo; output grows by five seconds.

def test_image_cta_endcard_uses_output_aspect(self):
    # Append CTA image; final frame matches 160x90 output resolution.
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest test.services.test_studio_render.StudioRenderTest.test_text_cta_endcard_contains_logo_and_last_five_seconds test.services.test_studio_render.StudioRenderTest.test_image_cta_endcard_uses_output_aspect`

Expected: FAIL because CTA composition does not exist.

- [x] **Step 3: Write minimal implementation**

Implement `append_cta(video_path, params, folder, resolution, fps)`. Text/logo and image render for five seconds. Video renders at most fifteen seconds and keeps its source audio. `longform_pipeline.run` calls it after the main composition and records final duration.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest test.services.test_studio_render`

Expected: PASS.

### Task 4: Controles no Estúdio

**Files:**
- Modify: `webui/studio.py`
- Test: `test/services/test_studio_ui.py`

- [x] **Step 1: Write the failing UI test**

```python
def test_production_uses_channel_text_cta_and_logo(self):
    # AppTest saves text CTA and logo, then asserts submitted params carry both fields.
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest test.services.test_studio_ui.StudioUITest.test_production_uses_channel_text_cta_and_logo`

Expected: FAIL because the UI does not forward visual CTA settings.

- [x] **Step 3: Write minimal implementation**

Add logo upload, CTA mode, and CTA asset upload to the channel identity form. Add per-video CTA mode/text/asset controls in script preparation. Persist the choice in editorial metadata and pass it to `build_production_params`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest test.services.test_studio_ui`

Expected: PASS.

### Task 5: Verification and documentation

**Files:**
- Modify: `AGENTS.md`
- Test: `test/services/test_studio.py`, `test/services/test_studio_ui.py`, `test/services/test_studio_render.py`, `test/services/test_longform_pipeline.py`

- [x] **Step 1: Update project memory**

Record supported formats, endcard durations, asset copying and compatibility without assets.

- [x] **Step 2: Run verification**

Run: `uv run python -m unittest test.services.test_studio test.services.test_studio_ui test.services.test_studio_render test.services.test_longform_pipeline; uv run python -m compileall app/services/editorial.py app/services/studio.py app/services/longform_media.py app/services/longform_pipeline.py webui/studio.py; git diff --check`

Expected: all tests pass, compilation succeeds, and diff check is empty.
