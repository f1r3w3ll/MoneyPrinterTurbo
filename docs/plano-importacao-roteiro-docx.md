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
- [ ] 4. `app/services/alignment.py`: dado o `sub_maker`/legendas geradas
      (edge-tts word boundaries ou whisper) + a lista de cenas com texto
      planejado, localizar o instante real de início de cada cena no
      áudio gerado (reaproveita a lógica de correspondência já usada em
      `subtitle.correct`)
- [ ] 5. `app/services/video.py`: novo modo de montagem que respeita
      timeline explícita por imagem (start/end reais), em vez do
      preenchimento aleatório/sequencial genérico atual
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
