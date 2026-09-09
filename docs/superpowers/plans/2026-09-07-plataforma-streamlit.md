# Plataforma Streamlit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Entregar criação, revisão, produção, retomada e download de vídeos longos na interface existente.

**Architecture:** Página Streamlit dedicada, serviço de produções persistentes e pipeline long-form isolado. Reutilizar a fila de tarefas e serviços de IA existentes. Manter o fluxo original.

**Tech Stack:** Python 3.11, Streamlit, Pydantic, MoviePy 2, Pillow, FFmpeg, unittest.

## Contratos de integração

`app.services.studio` expõe `save_draft(script: dict, draft_id=None) -> dict`, `list_drafts() -> list[dict]`, `submit(params: LongFormVideoParams) -> str`, `resume(task_id: str)`, `list_productions() -> list[dict]`, `get_production(task_id) -> dict`, `validate_settings(params) -> list[str]`. Registros possuem `id`, `title`, `status` (queued/running/failed/interrupted/complete), `phase`, `progress`, `error`, `params`, `artifacts`, `created_at`, `updated_at`. Artefatos: `video`, `thumbnail`, `script`, `subtitles`, `duration_seconds`. Rascunhos: `id`, `script`, `updated_at`.

Configuração usa `app.services.studio_settings`: `get_settings() -> dict` retorna modelos, URLs, configured e chaves vazias; `save_settings(values: dict)` preserva chaves vazias. Seções llm por provedor, image_generation e premium_tts. Valores mascarados nunca são credenciais.

## Tarefas

- [x] 1. Regressões: `test/services/test_longform_pipeline.py` cobre conclusão integral, falha de thumbnail, cena sem imagem, checkpoint atômico, sincronização e mídia sintética. Executar antes da implementação; confirmar falhas de comportamento.
- [x] 2. Implementar `app/services/longform_pipeline.py` e `longform_media.py`. Pipeline por cena para vínculo exato de áudio, imagem e legenda; reaproveitar arquivos validados por checkpoint, gerar legendas reais e vídeo em blocos limitados. Encaminhar `task.start_longform` para o novo serviço e corrigir stop_at nas rotas. Testar com `.venv/Scripts/python.exe -X utf8 -m unittest test.services.test_longform_pipeline`.
- [x] 3. Implementar `studio.py` e `studio_settings.py` com testes `test_studio.py`: persistência atômica, UUID, credenciais ausentes dos registros, configuração sem sobrescrever chave por máscara, prevenção de retomada duplicada e restauração após reinício. Usar fila local compartilhada por módulo.
- [x] 4. Implementar `webui/studio.py` e módulos auxiliares, navegação no início de `webui/Main.py`. Interface PT-BR: tema e providers, editor de cenas, rascunhos, configurações, acompanhamento por fragmento, player e downloads. Testes `test_studio_ui.py` com AppTest e serviços externos simulados.
- [x] 5. Revisar integração contra proposta; revisar qualidade; corrigir achados. Executar compilação, testes novos e seleção existente do CI. Renderizar vídeo sintético local para provar duração, áudio e legendas sem APIs pagas.
- [x] 6. Documentar uso e limitações verificadas em `LONGFORM_README.md`, atualizar proposta/plano com resultados. Abrir interface local para verificação quando disponível.

## Decisões de execução

Trabalhar nos arquivos locais existentes, preservando toda alteração anterior: a extensão ainda não rastreada é a base desta implementação. Não criar um checkout a partir de HEAD que perderia essa base. Nenhuma chamada paga ou publicação automática faz parte da verificação. Não incluir credenciais nem alterações anteriores em commits automáticos.

## Resultado da verificação — 07/09/2026

37 testes executados: OK, 1 optativo ignorado. Compilação de app, CLI, webui e testes passou. uv lock --check --offline passou (134 pacotes). Renderização sintética real validou vídeo, áudio, legendas e thumbnail. Interface conferida no navegador e com AppTest. Chamadas externas e benchmark de 30 minutos não foram executados. MoviePy emitiu ResourceWarning de leitores no encerramento; os testes de mídia passaram. Guia atual: docs/STUDIO.md.
