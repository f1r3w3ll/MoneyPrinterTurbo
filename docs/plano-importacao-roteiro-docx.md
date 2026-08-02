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
- [ ] 6. `app/services/task.py`: novo fluxo que orquestra
      parse docx -> gera áudio -> alinha cenas -> casa imagens por ordem
      -> monta vídeo com timeline explícita -> aplica BGM/legenda como hoje
- [ ] 7. `app/controllers/v1/video.py`: endpoint(s) novos para upload do
      `.docx` e do lote de imagens ordenado, reaproveitando o máximo do
      pipeline `/v1/videos` existente
- [ ] 8. Testes automatizados (`test/services/test_script_import.py`,
      `test/services/test_alignment.py`, ajustes em `test_video.py`)
- [ ] 9. WebUI (`webui/Main.py`): upload do `.docx`, preview da tabela de
      cenas, upload ordenado de imagens, indicação do timing calculado
- [ ] 10. Atualizar README/documentação do novo fluxo

## Notas técnicas

- Timestamps do docx são estimativas (145 wpm) — nunca usar diretamente
  como tempo final; sempre realinhar contra o áudio real.
- Áudio externo continua sem legenda automática nesta rodada (decisão do
  usuário) — não alterar `generate_subtitle`/`custom_audio_file` agora.
- BGM já atende (biblioteca local `resource/songs`, royalty-free) — sem
  mudanças necessárias.
