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
- A duração real do MP4 aparece em Produções e Publicação como informação,
  junto de tamanho e data/hora. A publicação não bloqueia um vídeo concluído
  por duração: a conferência da meta fica na revisão e antes de iniciar a
  produção, onde ainda evita custo com um roteiro fora do planejamento.
- O upload direto da WoopSocial sofreu um `524` do Cloudflare para um MP4 de
  55,4 MB, mesmo abaixo do limite documentado de 100 MB. Para MP4s a partir de
  25 MB, `woopsocial.py` usa a sessão de upload em partes com URLs
  pré-assinadas e espera a mídia ficar pronta antes de criar o post. Esse fluxo
  suporta arquivos de até 5 GB segundo a documentação atual da API.
- A aba Publicação exibe uma barra de progresso durante o envio: bytes enviados
  e percentual por parte, depois o processamento da mídia e a criação do post.
- O upload em partes repete somente a parte que falhar por erro transitório de
  rede ou gateway (`408`, `429`, `5xx`, incluindo `504`), com até quatro
  tentativas e espera progressiva. As partes já concluídas não são reenviadas.

## Idioma por vídeo — 10/09/2026

- A pauta tem um seletor explícito de idioma do vídeo: Português (Brasil),
  Inglês (EUA), Alemão e Espanhol. Ele usa o idioma do canal apenas como
  valor inicial, para que um tema em português não herde automaticamente a
  identidade inglesa do canal.
- A escolha acompanha a geração de pauta, embalagem, roteiro, narração,
  legendas e metadados de publicação. A etapa de roteiro mostra o idioma
  definido na pauta para evitar divergência; produções sem pauta preservam o
  seletor manual existente. Foram adicionadas embalagens em alemão e vozes
  padrão `de-DE-ConradNeural` e `de-DE-KatjaNeural`.

## Duração mínima — 10/09/2026

- Vídeos do Estúdio e os endpoints long-form aceitam de 5 a 30 minutos
  (300–1.800 segundos). O mínimo foi aplicado ao slider de roteiro, editor
  manual, parser, validação da API, avisos de produção e bloqueio de
  publicação, para manter o fluxo consistente.

## CTA visual e identidade do canal — 11/09/2026

- Cada canal pode cadastrar uma logo (`PNG`, `JPG`, `WEBP`) e escolher o CTA
  padrão: texto, imagem em tela cheia ou vídeo. Os ativos ficam em
  `storage/studio/channel_assets/<canal>/` e não entram no Git.
- O CTA pode ser ativado no roteiro e ter texto e formato visual ajustados por
  vídeo. O roteiro conserva a escolha para a produção, junto com a logo e o
  ativo visual selecionados.
- Antes de enfileirar o trabalho, o Estúdio copia logo e mídia de CTA para a
  pasta da produção. Assim, edições posteriores no perfil do canal não mudam
  um vídeo já iniciado ou que será retomado.
- Depois da composição, o pipeline acrescenta uma endcard: texto por cinco
  segundos, com logo centralizada e chamada abaixo; imagem por cinco segundos;
  ou vídeo de CTA de até quinze segundos, preservando seu áudio. Sem CTA
  configurado, o vídeo continua com o comportamento anterior.

## Recuperação de lote incompleto de roteiro — 10/09/2026

- Roteiros com mais de 12 cenas continuam gerados em lotes e não aceitam um
  lote parcial silenciosamente. Se um provider devolver menos cenas que as
  solicitadas, como 8 em vez de 12, o Estúdio repete somente aquele lote uma
  vez com a exigência explícita de quantidade. Uma segunda resposta incompleta
  encerra a geração com erro; não há loop de tentativas.

## ElevenLabs e certificados no Windows — 10/09/2026

- Uma falha de narração na primeira cena foi diagnosticada como
  `CERTIFICATE_VERIFY_FAILED`: o ambiente Python não confiava no certificado
  apresentado pela rede local/VPN. O cliente ElevenLabs agora incorpora os
  certificados confiáveis do repositório do Windows somente nesse cliente,
  mantendo a validação HTTPS ativa. Uma síntese curta com a voz inglesa
  configurada confirmou a geração de MP3 após a correção.

## Movimento visual e CTA configurável — decisão aprovada em 10/09/2026

- O Estúdio passará a oferecer, por vídeo, uma opção desativada por padrão para
  abertura animada. Nesta etapa ela aplicará movimento cinematográfico mais
  intenso às primeiras cenas do gancho, sem exigir uma nova API de vídeo; o
  restante do vídeo continuará usando imagens estáticas com movimento suave.
- O movimento local deve aplicar aproximação, afastamento ou deslocamento suave
  e transições reais às imagens durante a composição. Ele não deve exigir uma
  API adicional e será o comportamento visual padrão fora da abertura animada.
- A abertura animada precisa permanecer limitada a poucas cenas curtas para
  conter custo, tempo de processamento e inconsistências visuais. A interface
  deve comunicar a escolha e seu efeito. Uma futura integração de clipes de IA
  poderá aproveitar esses mesmos metadados, mas não fará parte desta etapa sem
  um provider de vídeo configurado pelo usuário.
- Configurações ganhará um texto de CTA padrão por canal. Ao gerar um roteiro,
  esse CTA será sugerido no idioma/configuração escolhidos e continuará
  editável no roteiro antes de iniciar a produção. O usuário poderá optar por
  usá-lo em cada vídeo, em vez de obrigar sua inserção.
- Implementado: a composição cria pan/zoom determinístico para todas as imagens
  e aplica `fade`, `slide` e `zoom` declarados no roteiro. Ao marcar
  **Abertura animada** na produção, as três primeiras cenas recebem movimento
  mais intenso, sem nova chamada de API. A duração do áudio continua sendo a
  duração efetiva da cena e as legendas ficam sobre os frames em movimento.
- Implementado: a identidade editorial tem campo **CTA padrão do canal**. O
  campo começa vazio; quando escolhido para um roteiro, a frase pode ser
  alterada e é inserida somente na cena CTA, preservando a edição posterior do
  roteiro. O valor escolhido acompanha os metadados da produção.

## Diagnóstico de créditos ElevenLabs — 11/09/2026

- A falha observada com a voz masculina inglesa `wBXNqKUATyqu0RtYt25i` não foi
  causada pela voz: a primeira cena foi sintetizada e a segunda foi recusada
  pela ElevenLabs por `quota_exceeded` (18 créditos disponíveis para uma cena
  que exigia 95). O Estúdio passa a preservar essa mensagem de cota durante a
  produção, em vez de mostrá-la apenas como falha genérica da cena.
- A chave atualmente configurada não possui a permissão `voices_read`, então
  o aplicativo não deve depender de consulta ao catálogo da ElevenLabs para
  pré-validar IDs de voz. A síntese pode continuar autorizada quando há saldo.

## Claude e certificados no Windows — 11/09/2026

- A indisponibilidade recorrente do Claude foi confirmada como
  `CERTIFICATE_VERIFY_FAILED`: a rede/VPN apresenta um certificado
  autoassinado que o repositório padrão do Python não reconhece. A chave, o
  modelo `claude-sonnet-4-6` e o endpoint oficial estavam corretos.
- O gerador de roteiro agora fornece ao SDK Anthropic um cliente HTTPX que
  incorpora os certificados da store `ROOT` do Windows, mantendo a validação
  TLS ativa. Uma consulta não geradora a `GET /v1/models` respondeu `200` e
  retornou 11 modelos após a correção.
- O SDK também herdava `ANTHROPIC_BASE_URL=http://127.0.0.1:3456` quando o
  campo de endpoint do Estúdio estava vazio. Esse proxy local não estava em
  execução e produzia `WinError 10061`. O gerador agora define explicitamente
  `https://api.anthropic.com` como padrão, preservando um endpoint customizado
  apenas quando ele for salvo em Configurações. Uma chamada mínima de mensagens
  com `claude-sonnet-4-6` foi concluída após a correção.

## Vocabulário de transições Claude — 11/09/2026

- O parser normaliza também `fade_to_black` e `fade-to-black`, retornados por
  Claude em roteiros longos, para a transição suportada `fade` antes da
  validação das cenas.

## Persistência concorrente do Estúdio — 11/09/2026

- Duas instâncias Streamlit foram encontradas escutando a porta 8501 e
  atualizando a mesma produção. O nome fixo `production.tmp` permitia colisão
  entre elas e causava `WinError 5` ao substituir `production.json`.
- O gravador JSON agora usa um arquivo temporário exclusivo no diretório de
  destino e repete brevemente a substituição em bloqueios transitórios do
  Windows. A aplicação deve operar com uma única instância Streamlit.

## Manutenção de transições e CTA — 11/09/2026

- O pipeline encaminha as transições normalizadas do roteiro para a composição,
  inclusive ao carregar checkpoints anteriores. Mudanças na transição invalidam
  apenas a composição, preservando áudio e imagens.
- O CTA usa as dimensões do vídeo base, preserva esse arquivo para retomada e
  retorna um MP4 separado com sufixo `-with-cta`. Não substitui arquivos enquanto
  os leitores do MoviePy estão abertos. A duração inclui a endcard.
- A retomada reutiliza a composição base após falha de CTA e o vídeo final após
  falha de thumbnail. Produções concluídas não são migradas automaticamente.
- As duas produções locais de 11/09 às 21:35 e 21:44 falharam na fase de imagens
  com `Connection error.`. Essa mensagem não comprova falha de certificado ou
  causa específica de rede; não atribuí-la à composição ou ao CTA.

## Retomada, exclusão e conexão de imagens — 11/09/2026

- Criar vídeo oferece retomada por título/data e Apagar projeto ao lado, com
  confirmação de exclusão permanente. O acompanhamento de falhas oferece as
  mesmas ações; a exclusão mantém a proteção do serviço para trabalhos ativos.
- Uma consulta HTTPS sem credenciais à OpenAI reproduziu
  CERTIFICATE_VERIFY_FAILED. O cliente de imagens agora incorpora certificados
  ROOT do Windows autorizados para servidor, mantendo verificação TLS ativa.
  A mesma consulta após a correção respondeu 401 (esperado sem chave), confirmando
  a conexão HTTPS. Não foi feita geração paga para validar esta correção.

## Isolamento dos testes do Estúdio — 12/09/2026

- Os testes de UI do painel de recuperação resolviam `app.services.studio`
  pelo atributo do pacote pai quando `test_studio` executava antes, ignorando
  o módulo falso injetado em `sys.modules`; o backend real retornava lista
  vazia e os botões de recuperação não eram renderizados (`KeyError`). Os
  scripts dos testes agora resolvem o módulo com `importlib.import_module`,
  seguindo o padrão de `webui/studio.py`. Seleção completa do CI: 96 testes
  OK. `TemporaryDirectory` usa `ignore_cleanup_errors=True` para evitar falha
  de limpeza no Windows com arquivos ainda abertos por leitores.

## Manutenção de documentação e dependências — 12/09/2026

- Divergências do registro inicial revalidadas: checkpoint já usa `os.replace`
  (sem janela sem checkpoint); rotas novas executam até thumbnail; DALL-E tem
  fallback de chave; `anthropic`, `elevenlabs` e `replicate` constam em
  `requirements.txt`; g4f é extra opcional do pyproject com import tardio e
  guarda explícita em `llm.py` — a exclusão do `requirements.txt` é intencional.
- `README-ar.md` deixou de instruir instalação de ImageMagick (legado desde a
  migração para MoviePy 2/Pillow) e seu troubleshooting agora orienta atualizar
  o código; numeração das etapas de instalação ajustada.
- Os exemplos de monitoramento em `LONGFORM_README.md` e
  `LONGFORM_VIDEO_DOCUMENTATION.md` tratavam HTTP 404 de checkpoint como
  conclusão e citavam um campo `num_completed_scenes` inexistente. Agora
  acompanham `status`/`current_phase`/`progress` até `completed`, `failed` ou
  `interrupted`, alinhados ao contrato real de `GET /checkpoint-status/{task_id}`
  e a `docs/STUDIO.md`: ausência de checkpoint ou 404 nunca significa sucesso.
- Midjourney, Play.ht e Murf seguem fora da interface por decisão de escopo; a
  seleção de TTS premium ocorre pelo prefixo `elevenlabs:<voice_id>` em
  `voice_name`, com validação em `studio_settings.py`, sem necessidade de
  encaminhar `premium_tts_provider` a `voice.tts`.

## Fail-fast de providers reservados — 12/09/2026

- `ImageGenerationService` agora valida o provider no `__init__`: `midjourney`
  e nomes desconhecidos falham imediatamente com `ValueError` claro, em vez de
  `NotImplementedError` no meio da geração. O método morto `_generate_midjourney`
  foi removido; comentários em `schema.py` e `config.example.toml` marcam
  midjourney/playht/murf como reservados e sem implementação nesta build (as
  chaves seguem no TOML apenas para não invalidar `config.toml` existentes).
  O Estúdio já rejeitava esses providers em `studio_settings.py`; a mudança
  protege o caminho direto da API (`/longform-videos`).
- `_record_task_analytics` em `task.py` tinha dois blocos `if result.get("video")`
  redundantes que sobrescreviam a lista `videos` com um item único quando ambos
  os campos existiam; agora usa `elif`, preservando a lista completa.
- Seleção completa do CI: 96 testes OK. Sem necessidade de reiniciar o Streamlit:
  as mudanças afetam apenas caminhos de erro inalcançáveis pela interface.

## Arquivamento de publicados — 12/09/2026

- Produções concluídas e publicadas são arquivadas fora do aplicativo em
  `D:/MoneyPrinterturbo/PUBLICADOS/<slug>/`, com `video.mp4` (versão final com
  CTA), `thumbnail.jpg`, `roteiro.json` e `descricao-youtube.txt`. A pasta da
  produção em `storage/studio/productions` é então removida por inteiro
  (áudios, imagens, MP4 intermediário, checkpoints e locks), liberando disco.
  O Estúdio deixa de listar a produção arquivada.
- A aba Publicação agora grava `publication.json` na pasta da produção após o
  envio à WoopSocial (título, descrição, tags, privacidade, projeto, conta e
  data/hora), para que a descrição exata publicada não dependa da sessão do
  navegador. Falha ao gravar não bloqueia a publicação (apenas avisa).
- Requer restart do Streamlit para produções futuras passarem a gravar
  `publication.json`.

## Publicação agendada e arquivamento — 12/09/2026

- Publicações agendadas (`privacy='scheduled'`) eram enviadas à WoopSocial com
  `privacy: private`, e o vídeo ia ao ar como privado. Agora o payload usa
  `privacy: public` com `SCHEDULE_FOR_LATER`: quando a data chega, o vídeo
  torna-se público.
- Nova ação `archive_production` em `studio.py` (botão "Arquivar como publicado"
  na aba Publicação, com confirmação): move `video.mp4`, `thumbnail.jpg`,
  `roteiro.json` e `descricao-youtube.txt` (montada a partir de
  `publication.json`) para `D:/MoneyPrinterturbo/PUBLICADOS/<id>/` e remove a
  pasta da produção. Recusa produções em fila ou em execução. O destino padrão
  é `Path(config.root_dir).parent / 'PUBLICADOS'`.
- `delete_production` e o arquivamento usam `_rmtree_production`, que repete a
  remoção após 1s em `OSError` (Windows às vezes recusa `rmdir` por arquivo
  ainda solto, WinError 145).
- Todos os `TemporaryDirectory` dos testes usam `ignore_cleanup_errors=True`
  (flake de teardown no Windows com arquivo ainda aberto por leitores).
- Falha pré-existente fora do CI: `test_voice.test_gemini_tts_uses_legacy_
  submaker_fields` retorna `None` por ausência de `storage/temp/tts-gemini-
  Zephyr.mp3` no ambiente; não relacionada às mudanças desta data.
- Seleção completa do CI: 99 testes OK. Mudanças na WebUI exigem restart do
  Streamlit para valer (botão de arquivamento e persistência de
  `publication.json`).
