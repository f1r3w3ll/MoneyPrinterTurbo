# Plano: Importação de roteiro (.docx) + imagens com timing por cena

Contexto: permitir que o MoneyPrinterTurbo receba um roteiro em Word (com
tabela de cenas: timestamp planejado + prompt de imagem) e um lote de
imagens estáticas, casando cada imagem com o trecho de tempo real em que
ela deve aparecer no vídeo — usando o áudio (TTS ou externo) já suportado
pelo projeto e a música de fundo local já existente.

Decisões já tomadas com o usuário:
- Alinhamento do tempo real de cada cena: por **texto** (localizar cada
  cena no timeline real de palavras do TTS/whisper), não só escala
  proporcional dos timestamps do docx.
- Áudio externo: por enquanto **sem** legenda automática (mantém
  comportamento atual). Não mexer nisso nesta rodada.
- Associação imagem → cena: **automática por ordem** de upload/lote,
  casando 1:1 com a ordem das cenas da tabela do docx.

Status geral: **em andamento**. Cada item abaixo é atualizado
(`[ ]` → `[x]`) conforme concluído, com o commit correspondente, para que
o trabalho possa ser retomado em outra máquina/sessão a qualquer momento.

## Tarefas

- [x] 1. Adicionar dependência `python-docx` (pyproject.toml + requirements.txt)
      — commit `200072c`
- [x] 2. `app/services/script_import.py`: parser de `.docx` -> roteiro completo
      (string) + lista de cenas `{scene_id, order, narration,
      planned_start_seconds, summary, image_prompt}` — commit `3e66f89`.
      Validado com o pacote real do usuário (23 cenas, todos os prompts de
      imagem casados corretamente). `ScriptScene.narration` guarda o texto
      da cena (não só o resumo da tabela) para servir de âncora ao
      alinhamento por texto na tarefa 4.
- [x] 3. `app/models/schema.py`: novos modelos/campos — commit `cac09b4`
      - `ScriptScene` (BaseModel): scene_id, order, narration,
        planned_start_seconds, start_seconds/end_seconds (preenchidos pelo
        alinhamento), summary, image_prompt
      - `VideoParams.video_scenes: Optional[List[ScriptScene]]`
      - `MaterialInfo.start_time`/`end_time` (Optional[float]) para
        posicionamento explícito na timeline
      - Nota: ficou decidido NÃO usar uma flag `scene_timeline_enabled`
        separada — a tarefa 5/6 vai detectar o modo "timeline explícita"
        pela simples presença de `start_time`/`end_time` em todos os
        materiais, mantendo o comportamento atual como default quando
        ausentes. Ajustar aqui se essa decisão mudar durante a tarefa 5.
- [x] 4. `app/services/alignment.py` — commit `6ebedf2`. Em vez de
      reimplementar alinhamento de fala, reaproveita o arquivo de legenda
      que o MPT já gera (`voice.create_subtitle`/`subtitle.create` +
      `subtitle.correct`), que sempre produz 1 entrada de SRT por
      sentença, na ordem da narração. `align_scenes_to_subtitle()` divide
      a narração de cada cena nas mesmas sentenças (mesma normalização —
      `utils.normalize_script_for_subtitle_matching` +
      `split_string_by_punctuations`) e caminha cumulativamente pelas
      entradas do SRT para achar o `start_seconds`/`end_seconds` real de
      cada cena. Validado contra o roteiro real: soma das sentenças por
      cena (370) bate exatamente com a contagem do script inteiro (370) —
      não há perda/duplicação de linhas no meio do caminho. Cenas que não
      conseguem alinhar (ex.: SRT mais curto que o esperado) ficam com
      `start_seconds`/`end_seconds = None` para o chamador decidir um
      fallback (tarefa 6).
- [x] 5. `app/services/video.py` — commit `1a1db28`
      - `preprocess_video()`: quando `MaterialInfo.start_time`/`end_time`
        estão preenchidos, a imagem usa essa duração real da cena em vez
        do `clip_duration` global (zoom também ajustado).
      - Nova `combine_videos_explicit_timeline()`: concatena os clipes já
        na ordem/duração corretas (sem escolha aleatória/sequencial, sem
        corte por `max_clip_duration`, sem loop), só faz resize para a
        resolução alvo (lógica extraída para `_resize_clip_to_target()`,
        reaproveitada também por `combine_videos()` — refactor puro, sem
        mudança de comportamento) e estica o último clipe se sobrar uma
        pequena diferença entre o fim da última cena alinhada e a duração
        real do áudio.
      - Testes novos em `test_video.py` cobrindo: duração da imagem vinda
        de start/end explícitos, esticamento do último clipe, e retorno
        antecipado sem clipes. Suíte completa: só a falha pré-existente
        (`test_gemini_tts_uses_legacy_submaker_fields`, não relacionada)
        continua falhando.
- [x] 6. `app/services/task.py` — commit `78be09d`
      - `alignment.finalize_scene_timeline()` (novo, em `alignment.py`):
        garante timeline completa/monotônica/sem gaps mesmo quando o
        alinhamento por texto falha em algumas cenas — usa escala
        proporcional dos `planned_start_seconds` do docx como base e
        sobrepõe os tempos reais alinhados onde disponíveis.
      - `task.align_imported_scenes()`: roda logo após a legenda ser
        gerada (`start()`, entre os passos 4 e 5), alinha
        `params.video_scenes` contra o `subtitle_path` recém-gerado,
        finaliza a timeline e fixa `start_time`/`end_time` em cada
        `MaterialInfo` de `params.video_materials`, casando por posição
        (ordem de upload = ordem das cenas).
      - `generate_final_videos()`: quando `params.video_scenes` está
        presente, usa `video.combine_videos_explicit_timeline()` em vez
        de `video.combine_videos()`.
      - Pipeline completo ponta a ponta: parse docx (tarefa 2, hoje feito
        fora do `task.py` — ver tarefa 7) -> gera áudio (TTS ou externo,
        já suportado) -> gera legenda (já suportado) -> alinha cenas
        (novo) -> preprocessa imagens com duração real por cena (tarefa 5)
        -> monta vídeo com timeline explícita (tarefa 5) -> BGM/legenda
        finais como hoje.
      - Limitação conhecida (não resolvida nesta rodada): se
        `preprocess_video` descartar alguma imagem (ex.: baixa resolução),
        a lista de vídeos baixados fica mais curta que `video_scenes` e o
        casamento posicional pode desalinhar as cenas seguintes. Aceitável
        por ora; documentar para o usuário validar resolução das imagens
        antes do upload.
      - Testes novos em `test_task.py` (`test_align_imported_scenes_*`) e
        em `test_alignment.py` (`test_finalize_scene_timeline_*`). Suíte
        completa: só a falha pré-existente continua falhando.
- [x] 7. `app/controllers/v1/video.py` — commit `cdef28b`
      - Novo `POST /v1/scripts/import`: recebe o `.docx`, chama
        `script_import.parse_docx_script()`, devolve `video_script` +
        `scenes` (JSON) para o cliente copiar direto em
        `VideoParams.video_script`/`video_scenes` numa chamada posterior a
        `POST /v1/videos`. Arquivo temporário salvo em
        `storage/script_imports/` e apagado logo após o parse (sucesso ou
        erro). `.docx` inválido -> 400 com a mensagem do
        `ScriptImportError`.
      - Renomeei a dataclass interna do parser de `ScriptScene` para
        `ParsedScene` (`app/services/script_import.py`) para não colidir
        de nome com o `ScriptScene` (pydantic) de `schema.py` — são
        estruturas diferentes (uma é a saída crua do parser, sem
        `start_seconds`/`end_seconds`; a outra é o modelo usado no
        `VideoParams`).
      - **Decisão**: não criei um endpoint novo para upload de imagem.
        `POST /v1/video_materials` já existe e já faz exatamente o
        necessário (recebe uma imagem, devolve o nome do arquivo já
        validado). O cliente só precisa chamar esse endpoint uma vez por
        imagem, **na mesma ordem das cenas**, e montar
        `VideoParams.video_materials` nessa ordem — é isso que
        `task.align_imported_scenes()` (tarefa 6) espera (casamento por
        posição). Se essa decisão mudar (ex.: quiser upload em lote numa
        única chamada), revisar aqui.
      - Testado ponta a ponta contra o pacote real do usuário (23 cenas,
        prompts corretos) e com `TestClient` via
        `test_script_import_endpoint.py` (sucesso, extensão inválida,
        docx sem seção de script). Suíte completa: só a falha
        pré-existente continua falhando.
- [x] 8. Testes automatizados — commit `e1105e9` (mais os commits das
      tarefas 2-7, que já incluíram testes unitários próprios)
      - `test_script_import.py`, `test_alignment.py`,
        `test_script_import_endpoint.py`: unitários, sempre rodam.
      - `test_video.py`: cobre `preprocess_video` com duração por cena e
        `combine_videos_explicit_timeline` (esticamento do último clipe,
        retorno antecipado sem clipes).
      - `test_task.py`: `test_align_imported_scenes_*` (unitário, sempre
        roda) + `test_task_docx_imported_scenes_end_to_end` (ponta a
        ponta com TTS real, seguindo o padrão existente
        `test_task_local_materials` — só roda com
        `MPT_RUN_INTEGRATION_TESTS=1`, pulado por padrão). Tentei rodar
        com a flag ligada neste ambiente: falhou por falta de acesso de
        rede ao edge-tts (timeout), não por erro de código — o pipeline
        chegou corretamente até a chamada de TTS com os parâmetros certos.
        Rodar de novo num ambiente com rede liberada para validar de
        ponta a ponta antes de considerar isso 100% confirmado em
        produção.
      - Suíte completa (`uv run python -m pytest test/`): 169 passed, 6
        skipped, só a falha pré-existente e não relacionada
        (`test_gemini_tts_uses_legacy_submaker_fields`) continua
        falhando.
- [x] 9. WebUI (`webui/Main.py`) — commit `1586a4e`
      - Novo expander "Import Script Package (.docx)" na seção de
        roteiro: upload do `.docx`, botão "Parse Script Package" que
        chama `script_import.parse_docx_script()` diretamente (mesmo
        processo, sem round-trip HTTP), preenche
        `st.session_state["video_script"]` e
        `st.session_state["video_scenes"]`, mostra tabela de preview
        (cena, início planejado, prompt de imagem) e botão para limpar.
      - Seção de upload de material local mostra aviso quando há cenas
        importadas, lembrando de enviar as imagens na mesma ordem da
        tabela.
      - Na submissão, `params.video_scenes` é reconstruído a partir do
        `session_state` e um aviso é mostrado se a quantidade de imagens
        enviadas não bater com a quantidade de cenas (mesma lógica de
        "casamento por posição" da tarefa 6).
      - Chaves de tradução novas adicionadas em `en.json`, `pt.json` e
        `ru.json` (o teste `test_webui_i18n.py` exige que toda chave
        usada em `tr()` exista em inglês e em russo). Outros idiomas
        (`de`, `es`, `id`, `tr`, `vi`, `zh`) ficam com fallback em inglês
        por ora — não bloqueiam nada, mas podem ser traduzidos depois.
      - Validado: app sobe limpo (`streamlit run webui/Main.py`, HTTP 200,
        sem erro nos logs) e suíte completa de testes passa (só a falha
        pré-existente continua falhando).
- [x] 10. Documentação — commit `0cdf570`
      - Nova seção "Importing a Script Package (.docx) with Timed Scenes"
        em `README-en.md` (entre "Background Music" e "Subtitle Fonts"):
        formato esperado do `.docx`, explicação de como o tempo real é
        calculado (alinhamento por texto + fallback proporcional), passo a
        passo via WebUI e via API (com exemplos `curl`), e a limitação de
        casamento por posição já registrada na tarefa 6/7.
      - Item novo na lista de Features.
      - **Decisão de escopo**: não traduzi para `README.md` (chinês) nem
        `README-ar.md` (árabe) — fica como próximo passo se for pedido;
        `README-en.md` é o readme "canônico" do `pyproject.toml`.

## Status final

Todas as 10 tarefas concluídas. Pipeline completo, testado e documentado:
`.docx` -> parser -> alinhamento por texto (com fallback proporcional) ->
timeline explícita por imagem -> montagem de vídeo -> API (
`POST /v1/scripts/import` + `POST /v1/videos`) -> WebUI. Suíte de testes:
169 passed, 6 skipped (testes de integração com TTS real, gated por
`MPT_RUN_INTEGRATION_TESTS`), 1 falha pré-existente e não relacionada
(`test_gemini_tts_uses_legacy_submaker_fields`).

Pontos em aberto para uma próxima rodada, se for o caso:
- Rodar o teste de integração ponta a ponta (`test_task_docx_imported_scenes_end_to_end`)
  num ambiente com acesso de rede ao edge-tts para confirmar 100% em
  produção (aqui só validei até a chamada de TTS, que falhou por falta de
  rede no sandbox).
- Robustez do casamento posicional imagem/cena quando `preprocess_video`
  descarta alguma imagem (baixa resolução) — hoje é aceito como limitação
  conhecida.
- Tradução da documentação para `README.md`/`README-ar.md` e para os
  demais idiomas do WebUI (`de`, `es`, `id`, `tr`, `vi`, `zh` ainda caem
  no fallback em inglês para as strings novas).

## Notas técnicas

- Timestamps do docx são estimativas (145 wpm) — nunca usar diretamente
  como tempo final; sempre realinhar contra o áudio real.
- Áudio externo continua sem legenda automática nesta rodada (decisão do
  usuário) — não alterar `generate_subtitle`/`custom_audio_file` agora.
- BGM já atende (biblioteca local `resource/songs`, royalty-free) — sem
  mudanças necessárias.
