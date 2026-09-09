# Editorial Channel Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add channel identity, editorial brief, packaging choices, and retention-aware scripting to the long-form Studio.

**Architecture:** Persist one local channel profile and attach an editorial brief plus selected packaging option to the generated structured script metadata. The existing long-form pipeline remains unchanged; it receives the enriched script only after the user selects an editorial angle and saves the script.

**Tech Stack:** Streamlit, Pydantic, local JSON persistence, existing multi-provider LLM service, unittest/AppTest.

---

### Task 1: Persist a channel profile

**Files:**
- Create: `app/services/editorial.py`
- Modify: `app/models/schema.py`
- Modify: `test/services/test_studio.py`

- [x] **Step 1: Write the failing test**

```python
profile = editorial.save_channel_profile({'name': 'Canal Atlas', 'niche': 'História da tecnologia'})
self.assertEqual(editorial.get_channel_profile()['name'], 'Canal Atlas')
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run python -X utf8 -m unittest test.services.test_studio.StudioTests.test_channel_profile_persists`

- [x] **Step 3: Write minimal implementation**

Create typed profile normalization and atomic storage at `storage/studio/channel_profile.json`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run python -X utf8 -m unittest test.services.test_studio.StudioTests.test_channel_profile_persists`

### Task 2: Create the editorial brief and packaging options

**Files:**
- Modify: `app/services/editorial.py`
- Modify: `webui/studio.py`
- Modify: `test/services/test_studio.py`
- Modify: `test/services/test_studio_ui.py`

- [x] **Step 1: Write the failing tests**

```python
options = editorial.packaging_options(brief)
self.assertEqual(len(options), 3)
self.assertTrue(all(option['thumbnail_text'] for option in options))
```

- [x] **Step 2: Run tests to verify failure**

Run: `uv run python -X utf8 -m unittest test.services.test_studio test.services.test_studio_ui`

- [x] **Step 3: Write minimal implementation**

Generate three editable, promise-aligned options locally; surface brief and option selection before script generation.

- [x] **Step 4: Run tests to verify success**

Run: `uv run python -X utf8 -m unittest test.services.test_studio test.services.test_studio_ui`

### Task 3: Generate and validate a retention-aware script

**Files:**
- Modify: `app/models/schema.py`
- Modify: `app/services/script_generator.py`
- Modify: `app/services/script_parser.py`
- Modify: `test/services/test_longform_pipeline.py`

- [x] **Step 1: Write the failing test**

```python
script = ScriptParser().parse_json_script(data)
self.assertEqual(script.metadata['editorial']['promise'], 'Entender por que isso mudou tudo')
```

- [x] **Step 2: Run test to verify failure**

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline.LongformTests.test_editorial_metadata_is_preserved`

- [x] **Step 3: Write minimal implementation**

Pass channel, brief and selected package into the script prompt; require hook, explicit promise, chapter reengagements, payoff, evidence note and visual function in script metadata.

- [x] **Step 4: Run tests to verify success**

Run: `uv run python -X utf8 -m unittest test.services.test_longform_pipeline`

### Task 4: Preserve editorial data through drafts and production

**Files:**
- Modify: `webui/studio.py`
- Modify: `app/services/studio.py`
- Modify: `test/services/test_studio_ui.py`

- [x] **Step 1: Write the failing test**

```python
self.assertEqual(saved_script['metadata']['editorial']['selected_package']['title'], 'Título escolhido')
```

- [x] **Step 2: Run test to verify failure**

Run: `uv run python -X utf8 -m unittest test.services.test_studio_ui`

- [x] **Step 3: Write minimal implementation**

Keep editorial metadata in Streamlit session, drafts, script export and production records.

- [x] **Step 4: Run the complete focused verification**

Run: `uv run python -m compileall app webui test` and `uv run python -X utf8 -m unittest test.services.test_studio test.services.test_studio_ui test.services.test_longform_pipeline`
