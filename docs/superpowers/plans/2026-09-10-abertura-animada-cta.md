# Abertura animada e CTA configurável Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Dar movimento cinematográfico a todas as cenas, intensificar opcionalmente o gancho e inserir um CTA padrão de canal que permanece editável no roteiro.

**Architecture:** A composição long-form passa a criar frames variáveis para cada imagem e aplicar a transição declarada sem alterar a linha do tempo do áudio. A preferência de abertura animada viaja como metadado do roteiro até `LongFormVideoParams`; o CTA é persistido no perfil editorial e incorporado ao contexto usado pelo gerador de roteiro.

**Tech Stack:** Python 3.11, Pydantic, Streamlit, Pillow, NumPy, MoviePy 2, unittest.

---

## Estrutura de arquivos

- `app/models/schema.py`: incluir a preferência de abertura animada em parâmetros de produção.
- `app/services/editorial.py`: persistir o CTA padrão no perfil de canal e fornecer valor inicial em inglês ao canal existente.
- `app/services/script_generator.py`: instruir e normalizar a cena CTA quando o contexto editorial fornece um CTA escolhido.
- `webui/studio.py`: editar CTA na identidade, escolher CTA e abertura animada por vídeo, gravar ambos nos metadados/parâmetros e apresentar a nova fase de composição.
- `app/services/longform_media.py`: produzir enquadramento animado, transições e legendas em cima de frames variáveis.
- `test/services/test_studio.py`: cobrir persistência de CTA, contexto de roteiro e metadados da abertura.
- `test/services/test_studio_render.py`: validar que a renderização de imagem muda no tempo, conserva áudio/duração e aceita transições.

### Task 1: Contratos editoriais e de produção

**Files:**
- Modify: `app/models/schema.py:412-450`
- Modify: `app/services/editorial.py:15-60`
- Test: `test/services/test_studio.py`

- [x] **Step 1: Write the failing tests**

```python
def test_channel_cta_is_persisted_with_each_profile(self):
    saved = editorial.save_channel_profile({'name': 'Canal Atlas', 'niche': 'Ciência', 'default_cta': 'Inscreva-se para o próximo episódio.'})
    self.assertEqual(saved['default_cta'], 'Inscreva-se para o próximo episódio.')
    self.assertEqual(editorial.get_channel_profile()['default_cta'], 'Inscreva-se para o próximo episódio.')

def test_longform_params_keep_animated_intro_choice(self):
    params = LongFormVideoParams(video_subject='Teste', animated_intro=True)
    self.assertTrue(params.animated_intro)
```

- [x] **Step 2: Run the targeted tests and confirm they fail**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_channel_cta_is_persisted_with_each_profile`

Expected: failure because `default_cta` is discarded by `_clean`.

- [x] **Step 3: Implement the minimal contracts**

```python
# schema.py, LongFormVideoParams
animated_intro: bool = False

# editorial.py, PROFILE_DEFAULTS
'default_cta': '',

# FIRST_CHANNEL_PROFILE
'default_cta': 'Subscribe for the next episode from Fio da Ciência.',
```

Keep `_clean`, `create_channel`, `get_channel_profile`, and `save_channel_profile` driven by `PROFILE_DEFAULTS`, so old JSON profiles gain an empty default and new profiles persist the value without a migration.

- [x] **Step 4: Run the focused tests**

Run: `uv run python -m unittest test.services.test_studio`

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add app/models/schema.py app/services/editorial.py test/services/test_studio.py
git commit -m "feat: persist channel CTA and animated intro choice"
```

### Task 2: CTA selection and script generation

**Files:**
- Modify: `webui/studio.py:89-315`
- Modify: `app/services/script_generator.py:260-325,563-594`
- Test: `test/services/test_studio.py`

- [x] **Step 1: Write the failing tests**

```python
def test_editorial_cta_is_in_prompt_and_final_cta_scene(self):
    request = ScriptGenerationRequest(
        topic='Data centers', language='en-US',
        editorial_context={'cta': {'enabled': True, 'text': 'Subscribe for the next episode.'}},
    )
    prompt = ScriptGeneratorService()._build_prompt(request)
    self.assertIn('Subscribe for the next episode.', prompt)
```

Also parse a five-scene generated payload with a `CTA` scene and assert the chosen CTA is present in that scene after `_parse_script_json`.

- [x] **Step 2: Run the targeted test and confirm it fails**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_editorial_cta_is_in_prompt_and_final_cta_scene`

Expected: failure because the CTA is not a dedicated editorial instruction.

- [x] **Step 3: Add editing controls and deterministic normalization**

In `_channel_profile_editor`, add `default_cta` to the existing profile form and to `editorial.save_channel_profile`. In `_script_sources`, show `Usar CTA padrão do canal neste roteiro` and an editable `CTA deste vídeo`; place `{'enabled': use_cta, 'text': cta_text}` in `editorial_context` and carry it into metadata.

In `_build_prompt`, add a directive that the exact chosen CTA belongs only in the scene whose `narrative_role` is `CTA`. In `_parse_script_json`, when `metadata.editorial.cta.enabled` and text are set, replace the CTA scene narration with the selected CTA; if no scene is marked CTA, append it to the final scene with a separating space. Preserve the existing language-specific legacy replacements only when no explicit CTA is selected.

- [x] **Step 4: Run CTA tests**

Run: `uv run python -m unittest test.services.test_studio`

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add webui/studio.py app/services/script_generator.py test/services/test_studio.py
git commit -m "feat: use editable channel CTA in scripts"
```

### Task 3: Cinematic movement and transitions in composition

**Files:**
- Modify: `app/services/longform_media.py:127-249`
- Test: `test/services/test_studio_render.py`

- [x] **Step 1: Write the failing render tests**

```python
def test_animated_image_changes_frame_without_changing_scene_duration(self):
    # Render a single scene with a visibly asymmetric image and 1 second audio.
    # Assert frames at 0.05 and 0.80 differ, clip duration remains 1 second,
    # and audio remains attached.

def test_intro_uses_stronger_motion_than_regular_scene(self):
    # Create two entries from the same asymmetric source with animated_intro=True.
    # Assert the first scene's frame displacement exceeds the second scene's.
```

- [x] **Step 2: Run the targeted test and confirm it fails**

Run: `uv run python -m unittest test.services.test_studio_render`

Expected: the two frames are equal because `frame_renderer` currently returns a static base image.

- [x] **Step 3: Implement deterministic motion and transitions**

Add a `motion_renderer(picture, size, entry, params, animated_intro)` that crops a slightly oversized `ImageOps.fit` canvas per time fraction and returns RGB NumPy frames. Choose pan direction from `entry['index'] % 4`; use a larger overscan only for the first three entries when `params.animated_intro` is true.

Refactor `frame_renderer` to receive a frame supplier rather than one static image, composite the caption over each generated frame, and cache only while both subtitle text and source frame time bucket are unchanged.

Create the `VideoClip` from that renderer. Apply `fade` with `video_effects.fadein_transition`, `slide` with `slidein_transition`, `zoom` with a short fade plus stronger initial crop, and leave `none` untouched. Keep every clip at `entry['duration']` and concatenate with `method='chain'` so total duration remains the sum of audio durations.

- [x] **Step 4: Run render tests**

Run: `uv run python -m unittest test.services.test_studio_render test.services.test_longform_pipeline`

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add app/services/longform_media.py test/services/test_studio_render.py
git commit -m "feat: animate long-form images and render transitions"
```

### Task 4: Wire the opening option into the production form and verify regression suite

**Files:**
- Modify: `webui/studio.py:403-455`
- Modify: `app/services/longform_pipeline.py:80-106` only if phase reporting needs a distinct pre-composition label
- Test: `test/services/test_studio.py`, `test/services/test_studio_render.py`

- [x] **Step 1: Write the failing metadata test**

```python
def test_production_submission_serializes_animated_intro(self):
    # Submit params assembled by the Studio path with animated_intro=True.
    # Assert saved record['params']['animated_intro'] is True.
```

- [x] **Step 2: Run the targeted test and confirm it fails**

Run: `uv run python -m unittest test.services.test_studio.StudioTests.test_production_submission_serializes_animated_intro`

Expected: failure because `_produce` does not expose or pass the option.

- [x] **Step 3: Implement form wiring**

Add an unchecked checkbox beside aspect/subtitle options in `_produce`:

```python
animated_intro = st.checkbox(
    'Abertura animada',
    value=False,
    help='Aplica movimento mais intenso às primeiras cenas do gancho, sem usar uma API adicional.',
)
```

Pass `animated_intro=animated_intro` to `LongFormVideoParams`. Add `composition` help text that explains that the opening receives stronger motion when selected. Do not change existing projects: stored parameters remain false by Pydantic default.

- [x] **Step 4: Run the full relevant regression suite**

Run:

```powershell
uv run python -m compileall app webui
uv run python -m unittest test.services.test_studio test.services.test_studio_render test.services.test_longform_pipeline test.services.test_studio_ui
```

Expected: PASS.

- [x] **Step 5: Commit and update memory**

```powershell
git add webui/studio.py app/services/longform_pipeline.py test/services/test_studio.py test/services/test_studio_render.py AGENTS.md
git commit -m "feat: offer animated opening in studio"
```


