# Contexto de continuidade com Codex

Registro inicial: 2026-09-07. Este arquivo consolida a leitura da documentação
local e uma conferência estática dos pontos principais no código. Não constitui
validação de execução ou certificação de produção.

## Direção do trabalho

- O usuário decidiu continuar o desenvolvimento com Codex, substituindo Claude
  como assistente de desenvolvimento. Trabalhar neste projeto, `finback`.
- Comunicar-se em português brasileiro.
- A decisão sobre o assistente não implica remover o provider Anthropic/Claude
  do produto; isso depende de uma solicitação específica de mudança funcional.
- Preservar alterações locais existentes. Na leitura inicial havia código
  modificado e serviços/documentos ainda não rastreados pelo Git.
- Não copiar ou expor credenciais de `config.toml` em documentação ou commits.

## Objetivo e arquitetura

Base: MoneyPrinterTurbo 1.3.0, gerador de vídeos curtos. A extensão pretende
produzir vídeos de 15–30 minutos para YouTube, com roteiro estruturado,
imagens por IA, narração, legendas, composição progressiva e thumbnail.
Preservar o funcionamento do pipeline original ao evoluir a extensão.

- Python: `>=3.11,<3.13`; runtime recomendado nos READMEs: 3.11.
- Dependências principais: `pyproject.toml`; resolução: `uv.lock`.
- Backend: FastAPI, Pydantic, controladores em `app/controllers/v1/`.
- Interface existente: Streamlit em `webui/Main.py`; CLI: `cli.py`.
- Vídeo: MoviePy 2.2.1, FFmpeg e Pillow.
- Serviços originais: `llm.py`, `material.py`, `voice.py`, `subtitle.py`,
  `video.py`, `task.py`, `state.py` e `upload_post.py`.
- Extensão: `script_generator.py`, `script_parser.py`,
  `image_generation.py`, `thumbnail.py`, `checkpoint.py` e alterações nos
  modelos, controlador de vídeo, configuração e orquestração.
- `analytics.py` já contém armazenamento JSONL e agregação de métricas;
  sua presença não significa que o dashboard planejado esteja implementado.

Fluxo long-form: roteiro → áudio → imagens → legendas → composição → thumbnail.
Áudio é agrupado por aproximadamente 5.000 caracteres. A composição prevê
blocos de cinco minutos e concatenação por FFmpeg. Checkpoints guardam a fase
e os artefatos para retomada.

## Contratos principais

`StructuredScript` contém título, descrição, duração estimada e cenas.
Cada `SceneInfo` contém índice, narração, prompt de imagem, duração opcional
e transição. O parser valida 5–100 cenas, duração estimada de 900–1.800 segundos,
narração de 10–2.000 caracteres, prompts de 3–1.000 caracteres e duração
por cena de 3–60 segundos quando informada. Essas validações não comprovam
a duração real do vídeo renderizado.

Rotas da extensão sob `/api/v1`:

- `POST /generate-script`
- `POST /validate-script`
- `GET /llm-config` e `POST /llm-config`
- `POST /longform-videos`
- `GET /checkpoint-status/{task_id}`
- `POST /resume-task/{task_id}`

Roteiro long-form usa `[llm.<provider>]`, com OpenAI, Claude, Gemini, DeepSeek,
Kimi e Qwen. O pipeline original usa configurações em `[app]`.
Imagens, TTS premium e processamento usam `[image_generation]`,
`[premium_tts]` e `[longform]`.

## Divergências verificadas na leitura inicial

Tratar as declarações antigas de “completo”, “100% compatível” e “produção
ready” como afirmações históricas ainda sujeitas a testes.

1. `test/test_longform.py` existe localmente, mas não apareceu no inventário
   padrão do Git/rg: conferir regras de ignore antes de concluir que falta
   um arquivo. Contém 14 métodos de teste pytest, incluindo um placeholder
   de thumbnail, em vez dos 15 testes anunciados. Não integra a seleção
   de testes unittest do CI. Há testes originais em `test/services/`.
2. `ImageGenerationService._generate_midjourney` termina em
   `NotImplementedError`. Há implementação de chamadas para DALL-E e
   Stable Diffusion, sem validação real das APIs nesta análise.
3. Play.ht e Murf aparecem em configuração/modelos, mas não foi encontrada
   implementação no serviço de voz. ElevenLabs tem implementação e depende
   de um pacote não declarado diretamente em `pyproject.toml` ou
   `requirements.txt`. A seleção efetiva ocorre por
   `voice_name="elevenlabs:<voice_id>"`; o agrupamento de áudio não encaminha
   `premium_tts_provider` para `voice.tts`.
4. As rotas de criação e retomada passam `stop_at="video"`; o pipeline
   retorna antes da fase de thumbnail nesse caminho.
5. DALL-E lê `[app].openai_api_key`; salvar somente `[llm.openai].api_key`
   pelo endpoint não configura a chave de imagens.
6. `CheckpointManager.save_checkpoint` remove o arquivo anterior antes de
   renomear o temporário. Existe uma janela sem checkpoint, apesar da
   documentação descrever substituição atômica.
7. O exemplo que considera HTTP 404 de checkpoint como conclusão é inadequado:
   ausência de checkpoint não prova sucesso. Além disso, `utils.get_response`
   monta um dicionário com campo `status`, sem definir por si só o status HTTP.
   Conferir o estado da tarefa e os artefatos para verificar conclusão.
8. A interface Streamlit original existe; falta sua integração long-form.
   CI e publicação Docker já existem em `.github/workflows/`, embora a
   memória antiga mencione CI/CD como trabalho futuro.
9. Docker instala `requirements.txt`, que não inclui a dependência Anthropic
   adicionada ao manifesto principal. O compose de release usa a imagem
   upstream e não incorpora automaticamente as alterações locais da extensão.
10. O README árabe ainda orienta instalar ImageMagick; READMEs inglês e chinês
    explicam a migração para MoviePy 2/Pillow. Há instruções legadas também
    nos arquivos de configuração e Docker.

Custos, benchmarks, disponibilidade dos modelos e “servidor ativo em 8081”
constantes nos documentos não foram verificados nesta análise. Não apresentá-los
como dados atuais ou resultados medidos.

## Execução e verificação

Executar comandos na raiz de `finback`:

```powershell
uv sync --frozen
uv run python main.py
# Interface original, em execução separada:
.\webui.bat
```

`listen_port` é uma chave no nível raiz do TOML; fallback do código: 8080.
A documentação da extensão usa 8081. Streamlit usa normalmente 8501.
Verificar configuração e processo reais antes de afirmar que estão ativos.

Verificações usadas pelo CI existente:

```powershell
uv run python -m compileall app cli.py main.py webui test
uv run python -X utf8 -m unittest test.services.test_state test.services.test_task test.services.test_schema test.services.test_webui_i18n
```

`test/README.md` documenta `unittest` e testes externos optativos via
`MPT_RUN_INTEGRATION_TESTS=1`. A leitura inicial não executou testes,
servidores, instalação de pacotes ou chamadas pagas de geração.

## Documentação assimilada

- `LONGFORM_VIDEO_DOCUMENTATION.md`: arquitetura, contratos, configuração,
  exemplos, operação, roadmap e estimativas da extensão.
- `LONGFORM_README.md`: início rápido e fluxo de uso.
- `DEVELOPMENT_MEMORY.md`: requisitos, decisões e histórico declarado.
- `PROJECT_SUMMARY.txt` e `FILES_CHANGELOG.md`: resumo e inventário declarado.
- `README.md`, `README-en.md`, `README-ar.md`: produto original, instalação,
  CLI/WebUI, materiais, vozes e troubleshooting; traduções divergem.
- `test/README.md`, `.github/SECURITY.md`, templates e workflows.
- `docs/voice-list.txt` e `docs/MoneyPrinterTurbo.ipynb`: catálogo local de
  vozes e guia Colab com ambiente isolado, Streamlit e ngrok.
- `config.example.toml`, manifestos, Dockerfiles, compose e licença MIT.

## Atualização após aprovação do estúdio — 07/09/2026

O usuário escolheu evoluir Streamlit e aprovou a proposta em
`docs/superpowers/specs/2026-09-07-plataforma-streamlit-design.md`.
Foi implementado `webui/studio.py`, com navegação no `webui/Main.py`, editor,
rascunhos, configuração, produção, histórico, retomada e downloads.

Os serviços atuais são `studio.py`, `studio_settings.py`, `studio_storage.py`,
`studio_lease.py`, `longform_pipeline.py` e `longform_media.py`.
Produções novas ficam em `storage/studio`; usam áudio por cena, legendas,
composição em blocos e thumbnail. O bloqueio de produção é por arquivo/OS;
as filas e configurações em memória são por processo. Consulte `docs/STUDIO.md`.

As divergências acima são o registro inicial: checkpoint agora usa os.replace;
rotas novas executam até thumbnail; DALL-E tem fallback de chave llm.openai;
ElevenLabs/Replicate e Anthropic constam nas dependências; testes do estúdio
foram adicionados ao CI. Midjourney, Play.ht e Murf continuam fora da interface.
O gerador original foi preservado.

- Em **Produções**, projetos concluídos, falhos ou interrompidos podem ser
  excluídos pela interface. A ação remove de forma permanente a pasta inteira
  em `storage/studio/productions`, incluindo vídeo, thumbnail, roteiro,
  legendas e checkpoints. Produções em fila ou em execução são protegidas.

## Atualização operacional e UX — 08/09/2026

- A seleção de roteiro Claude não envia `base_url=None` ao SDK; erros de conexão
  são apresentados com orientação específica. Os modelos padrão foram atualizados
  para Claude Sonnet 4.6 e Gemini 3.5 Flash.
- O parser normaliza a transição legada `cut` para `none` ao salvar roteiros.
- Geração de imagens OpenAI usa `gpt-image-1`, com adaptação de qualidade e
  tamanho para a API atual, incluindo respostas `b64_json`. Não reverter para
  `dall-e-3`, pois esse modelo retornou erro de inexistência nesta instalação.
- O Estúdio oferece quatro vozes predefinidas ElevenLabs e associa a voz ao
  identificador de produção. A configuração continua exigindo uma chave
  ElevenLabs válida; não registrar chaves nos arquivos do repositório.
- A etapa de produção oferece proporção Retrato/Paisagem e configuração de
  legendas: habilitação, fonte, posição, cores, tamanho, contorno e fundo.
- O fluxo visual apresenta as etapas Roteiro, Revisão, Produção e Download.
  Os controles de produção só aparecem após existir um roteiro e, quando uma
  produção é enviada, a tela mostra barra de progresso atualizada a cada dois
  segundos com a fase real do pipeline.
- Novas produções usam pasta e MP4 identificáveis pelo título em formato slug,
  data/hora e sufixo curto. IDs UUID anteriores continuam aceitos para retomar
  produções antigas. Não renomear artefatos já concluídos automaticamente.
- Uma produção real autorizada pelo usuário foi concluída com imagens, MP4 e
  thumbnail; chamadas de imagem podem gerar custos. Houve também uma produção
  antiga que falhou por usar `dall-e-3` e não deve ser retomada sem necessidade.
- Verificação recente: compilação dos arquivos alterados e 25 testes de
  `test_studio`, `test_studio_ui` e `test_longform_pipeline` passaram. Os testes
  do MoviePy podem emitir `ResourceWarning` de leitores de áudio, sem falhar.

## Fundação editorial do canal — 09/09/2026

- Antes desta evolução foi criada a tag local
  `backup/editorial-foundation-before-2026-09-09`, que preserva o commit
  `8f13746` como ponto de retorno do Estúdio anterior.
- O Estúdio suporta múltiplos canais. O índice e o canal ativo ficam em
  `storage/studio/channels.json`; cada perfil editorial fica em
  `storage/studio/channels/<id>.json`. Perfis legados em
  `storage/studio/channel_profile.json` são migrados automaticamente ao
  inicializar a estrutura, sem apagar o arquivo original.
- O primeiro canal ativo é `Fio da Ciência` (`fio-da-ciencia`), com conteúdo
  em inglês (`en-US`) no nicho *Science and technology explained*. Seu perfil
  define documentário claro, fontes qualificadas, explicação de sistemas e
  consequências práticas, com restrição a sensacionalismo, pseudociência e
  alegações sem evidência. O idioma do canal é o padrão da pauta e da narração,
  mas pode ser alterado para um vídeo específico.
- A interface permite criar canais, escolher o ativo e editar sua identidade:
  canal, nicho, recorte, público, promessa, tom, pilares, direção visual,
  política de fontes e restrições. A troca de canal reinicia apenas a pauta em
  edição; roteiros e produções existentes mantêm seus metadados.
- A criação começa com pauta (tema, pergunta, tese, promessa, objetivo e
  referências) e apresenta três opções editáveis de título, texto e conceito
  visual de thumbnail. A opção escolhida é vinculada ao roteiro para que a
  promessa e a thumbnail não se separem da entrega do vídeo.
- `SceneInfo` passou a aceitar papel narrativo, função visual, gancho em aberto
  e nota de fonte. O gerador instrui a IA a estruturar gancho, capítulos,
  mudanças de ritmo, payoff e notas de checagem. Os campos são opcionais para
  preservar roteiros e produções existentes.
- Metadados editoriais acompanham a sessão, o rascunho, a exportação do roteiro
  e os parâmetros de produção. A tela de revisão mostra uma checagem de
  promessa/gancho/payoff quando esses dados existem.
- A pauta tem o botão `Gerar pauta com IA`. Ele usa o mesmo provider de roteiro
  configurado pelo usuário e preenche pergunta central, tese, promessa,
  objetivo e direções de fontes a partir do tema e da identidade editorial.
  A resposta é apenas uma proposta editável: a interface orienta revisar fatos,
  fontes e promessa antes de gerar roteiro. Erro de JSON do provider não altera
  os campos da pauta.

## Duração e embalagem — 09/09/2026

- O campo de tema, o seletor de IA e o botão `Gerar pauta com IA` ficam na
  mesma linha da pauta, para iniciar o fluxo a partir do único dado necessário.
- A duração escolhida para um roteiro gerado por IA agora produz um orçamento
  de narração no prompt: taxa estimada por idioma, total de caracteres e faixa
  de caracteres por cena. O roteiro registra `script_language` e
  `target_duration_seconds` em seus metadados.
- Antes da produção, o Estúdio estima a duração a partir da narração e compara
  com a meta do roteiro gerado, com margem de 20%. Se estiver fora da faixa,
  avisa durante a revisão e não inicia voz, imagens ou vídeo. A duração do
  áudio produzido ainda é a medida definitiva.
- Títulos automáticos de embalagem são encurtados por palavra para até 70
  caracteres, evitando que temas longos sejam concatenados em títulos pouco
  legíveis. As sugestões continuam editáveis pelo usuário.
- Quando um roteiro gerado ficar fora da faixa de duração, a revisão oferece
  uma única ação `Ajustar duração com IA`. Ela reescreve somente a narração
  para o orçamento da meta e preserva a estrutura e os metadados. O contador
  fica no roteiro; após essa tentativa a interface exige ajuste manual, sem
  entrar em ciclos de chamadas à API.
- A correção de duração restaura prompts visuais, transições, durações por
  cena e campos narrativos técnicos do roteiro original; somente a narração
  retornada pela IA é aproveitada. Isso evita `duration_seconds` inválido.
  Chamadas OpenAI, DeepSeek, Kimi e Qwen de roteiro reservam 12.000 tokens de
  saída; Claude e Gemini usam 16.000. Isso acomoda roteiros longos em todos os
  providers disponíveis no Estúdio.
- O parser normaliza vocabulário comum de transições retornado por LLMs:
  `wipe`/`swipe` para `slide`, `dissolve`/`crossfade` para `fade` e cortes
  diretos para `none`. Transições não reconhecidas continuam sendo rejeitadas.
- Roteiros cuja meta exige mais de 12 cenas são gerados em blocos de no máximo
  12 cenas, com duração e orçamento de texto proporcionais. O resultado reúne
  os blocos em um único roteiro; um bloco que retorne menos cenas que o pedido
  falha explicitamente, em vez de produzir silenciosamente um vídeo curto.
- A faixa aceitável da estimativa textual é 75% a 120% da meta: por exemplo,
  uma meta de 20 minutos aceita 15 minutos ou mais, preservando a faixa
  long-form. O prompt exige CTA no idioma da narração; em roteiro inglês,
  `inscreva-se` em uma cena CTA é normalizado para `Subscribe`, sem alterar o
  nome de marca do canal.

## Publicação — 09/09/2026

- A aba Publicação usa o título editorial completo salvo em
  `metadata.editorial.selected_package.title` como título inicial do YouTube;
  `thumbnail_text` continua sendo apenas a frase curta sobreposta à imagem.
  Ambos permanecem editáveis antes do envio.
- Como as chamadas OpenAI são configuradas para responder em JSON, a geração
  de descrição pede explicitamente o campo `description` e a interface extrai
  apenas esse texto, sem expor JSON ao usuário.
- O cliente WoopSocial aceita respostas de canais tanto como lista no nível
  raiz quanto em envelopes `data`/`items`/`socialAccounts`.
- Para produções antigas sem `script_language`, a publicação usa o idioma
  do canal preservado em `metadata.editorial.channel.language`. A WoopSocial
  pode identificar o canal pelo campo `username`; a interface o prioriza em
  vez do ID técnico.
- O upload de mídia da WoopSocial requer `projectId` na query. A interface
  lista os projetos disponíveis e envia o MP4 ao projeto escolhido antes de
  criar o post. O payload atual do YouTube usa `title` e `privacy` diretamente
  no item de canal; agendamentos usam `SCHEDULE_FOR_LATER` e `scheduledFor`.
- Títulos de YouTube têm limite de 100 caracteres. O Estúdio encurta o título
  editorial automático por palavras, mostra a contagem e valida esse limite
  antes de iniciar o upload do MP4.
- A geração de descrição segue uma estrutura determinística: resumo, capítulos
  temporizados, pontos principais, fontes/notas, CTA e hashtags. A IA retorna
  dados estruturados e o Estúdio renderiza os blocos nessa ordem. As tags de
  busca ficam em um campo separado, editável, limitado a 15 itens e são
  enviadas no campo próprio do YouTube pela WoopSocial.
- Antes de criar o post, a integração chama `POST /posts/validate`. Uma
  rejeição é exibida com as mensagens da WoopSocial e não cria o post; isso
  substitui os erros HTTP 400 genéricos por orientação acionável.
- Erros HTTP do upload, validação e criação do post preservam o campo de
  detalhe devolvido pela WoopSocial (`error_message`, `message` ou `error`),
  em vez de expor somente a URL do endpoint.
- A resposta atual de `POST /media` contém o identificador em `mediaId`.
  A integração aceita também os formatos legados `id`, `data.id` e
  `media.id`, mas agora
  interrompe o fluxo antes da validação se nenhum identificador for retornado;
  assim nunca envia `mediaId: null` ao post.
- A aba Publicação agora confere a duração real do MP4 antes de liberar o
  envio. Se o arquivo estiver fora da faixa de 15–30 minutos ou fora da meta
  persistida para aquela produção, a interface bloqueia a publicação e mostra
  as durações real e planejada. A lista também mostra a duração de cada vídeo.
