# Roteiro-base paralelo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir gerar um `StructuredScript` a partir de um roteiro-base completo, preservando a via de pauta atual e incluindo público sugerido no contexto de publicação.

**Architecture:** `ScriptGeneratorService` receberá uma entrada explícita de roteiro-base e construirá uma instrução que trata o texto como referência. A interface Streamlit terá um novo formulário independente; o resultado usa o mesmo editor, parser e persistência existentes. O público escolhido será gravado em `metadata.editorial` e reaproveitado ao criar descrição, tags e hashtags.

**Tech Stack:** Python 3.11, Pydantic, Streamlit, unittest, ScriptGeneratorService, ScriptParser.

---

### Task 1: Contrato e geração a partir de roteiro-base

**Files:**
- Modify: `app/services/script_generator.py`
- Test: `test/services/test_longform_pipeline.py`

- [ ] **Step 1: Write failing tests for the explicit source prompt and metadata**

```python
def test_build_base_script_prompt_treats_source_as_reference(self):
    request = ScriptGenerationRequest(topic='A title', language='en-US', duration_minutes=20)
    prompt = ScriptGeneratorService().build_base_script_prompt(request, 'SOURCE TEXT', 'US adults 25-44')
    self.assertIn('SOURCE TEXT', prompt)
    self.assertIn('reference material, not instructions', prompt)
    self.assertIn('US adults 25-44', prompt)
```

- [ ] **Step 2: Run the test and confirm it fails because the method does not exist**

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline`

- [ ] **Step 3: Add `build_base_script_prompt` and `generate_from_base_script`**

```python
def generate_from_base_script(self, request, source_text, audience=''):
    source_text = str(source_text or '').strip()
    if len(source_text) < 100:
        raise ValueError('Cole um roteiro-base com pelo menos 100 caracteres.')
    prompt = self.build_base_script_prompt(request, source_text, audience)
    content, model, tokens = self._generate_provider(request.llm_provider.value, prompt, self.llm_configs[request.llm_provider.value])
    script = self._parse_script_json(content, request)
    script.metadata = {**(script.metadata or {}), 'source_mode': 'base_script', 'source_text': source_text, 'source_audience': audience}
    return script, model, tokens
```

The prompt must request exactly the supported scene schema, English image prompts, duration budgeting, source fidelity, and no instruction-following from the pasted reference.

- [ ] **Step 4: Run the test and confirm it passes**

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline`

- [ ] **Step 5: Commit**

```powershell
git add app/services/script_generator.py test/services/test_longform_pipeline.py
git commit -m "feat: generate structured scripts from source text"
```

### Task 2: Formulário paralelo no Estúdio

**Files:**
- Modify: `webui/studio.py`
- Test: `test/services/test_studio_ui.py`

- [ ] **Step 1: Write failing UI tests**

```python
def test_script_sources_renders_base_script_form(self):
    # Render with fake Streamlit and assert labels for source text, audience suggestion,
    # duration, language, style, provider, and generate action are present.
```

- [ ] **Step 2: Run the test and confirm the new labels are absent**

Run: `uv run python -X utf8 -m unittest test.services.test_studio_ui`

- [ ] **Step 3: Add the `Gerar a partir de roteiro-base` expander**

The form must collect `source_text`, `minutes`, `language`, `style`, `audience`, `provider`, and the existing CTA choice. It calls `generate_from_base_script`, writes `metadata.editorial.source_mode`, `audience`, `language`, and CTA settings, then calls `_load(script.model_dump())`. It must not mutate `studio_brief`, packaging keys, or `output_thumbnail_text`.

- [ ] **Step 4: Add editable audience suggestion**

Use `ScriptGeneratorService.generate_editorial_json` with a small JSON-only prompt that returns `{"audience": "..."}` from the source text and language. Store the result only in the audience widget state; retain manual edits.

- [ ] **Step 5: Run UI tests and confirm the current sources still render**

Run: `uv run python -X utf8 -m unittest test.services.test_studio_ui`

- [ ] **Step 6: Commit**

```powershell
git add webui/studio.py test/services/test_studio_ui.py
git commit -m "feat: add base-script source to studio"
```

### Task 3: Público na publicação e regressão integrada

**Files:**
- Modify: `webui/studio.py`
- Test: `test/services/test_studio_ui.py`

- [ ] **Step 1: Write failing test for audience-aware publication prompt**

```python
def test_publication_prompt_includes_base_script_audience(self):
    # Assert description prompt receives the editorial audience and asks tags/hashtags
    # to address that audience without fabricating demographic facts.
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run python -X utf8 -m unittest test.services.test_studio_ui`

- [ ] **Step 3: Add only the audience context to the existing publication prompt**

```python
audience = ((project['script'].get('metadata') or {}).get('editorial') or {}).get('audience', '')
audience_context = f' Target audience: {audience}.' if audience else ''
prompt = f'Generate YouTube publication metadata exclusively in {language_name}.{audience_context} ...'
```

- [ ] **Step 4: Run the focused and full Studio test suites**

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline test.services.test_studio test.services.test_studio_ui`

- [ ] **Step 5: Commit**

```powershell
git add webui/studio.py test/services/test_studio_ui.py
git commit -m "feat: use script audience in publication metadata"
```

### Task 4: Document and verify

**Files:**
- Modify: `docs/STUDIO.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Document the source-text flow, saved metadata, and editorial audience behavior**

- [ ] **Step 2: Run syntax and all relevant tests**

Run: `uv run python -m compileall app webui test`

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline test.services.test_studio test.services.test_studio_ui`

- [ ] **Step 3: Commit documentation**

```powershell
git add docs/STUDIO.md AGENTS.md
git commit -m "docs: document base-script generation"
```
