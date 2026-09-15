# Estúdio de vídeos longos

Interface local implementada em Streamlit, integrada ao pipeline de roteiro,
narração, imagens, legendas, vídeo e thumbnail. O gerador original continua
disponível na barra lateral.

## Iniciar

Na raiz de `finback`, com Python 3.11:

```powershell
uv sync --frozen
uv run python -m streamlit run webui/Main.py --server.address=127.0.0.1 --server.port=8501
```

Abra http://127.0.0.1:8501. Também é possível iniciar com `webui.bat`.
O estúdio chama os serviços Python diretamente; não exige iniciar FastAPI.
Para usar a API separadamente, execute `uv run python main.py` e consulte a
porta configurada por `listen_port` no nível raiz do TOML (fallback 8080).

## Produzir um vídeo

1. Em **Configurações**, informe as credenciais dos serviços escolhidos.
   Campos de chave vazios preservam o valor salvo. As chaves ficam no
   `config.toml` local e não são retornadas pela tela ou registradas na produção.
2. Em **Criar vídeo**, gere um roteiro com IA, importe JSON, crie um roteiro
   manual ou abra **Gerar a partir de roteiro-base**. A geração por IA oferece
   os seis provedores já integrados ao projeto.
3. Edite título, descrição, narração e descrição de imagem de cada cena.
   Use **Salvar roteiro** antes de produzir. É possível adicionar/remover cenas,
   exportar JSON e reabrir rascunhos salvos.
4. Escolha a fonte visual, voz, formato, legendas e estilo da thumbnail. Clique em
   **Gerar vídeo completo**. Chamadas externas podem consumir créditos.
5. Em **Produções**, acompanhe as etapas. Use **Atualizar histórico** para
   carregar o resultado final, abrir o player e baixar MP4, thumbnail, roteiro
   e SRT quando as legendas estiverem habilitadas.

## Serviços e duração

- Imagens: DALL-E/OpenAI ou Stable Diffusion 3.5 Large via Replicate. O
  Replicate executa o modelo na nuvem e requer créditos; uma instalação local
  de ComfyUI ainda não está ligada a esta tela. Midjourney não é oferecido
  porque sua implementação ainda não existe.
- Clipes gratuitos: Pexels, Pixabay e Coverr podem ser selecionados como fonte
  visual. Cada biblioteca exige sua própria chave de API, inserida em
  **Configurações**. O modo **Clipes gratuitos** usa somente esses vídeos; o
  modo **Híbrido** usa clipes em duas de cada três cenas e imagens por IA nas
  demais. A produção salva a fonte, URL e termo de busca de cada clipe em
  `artifacts.json`, além do arquivo baixado na própria pasta da produção. Um
  clipe indisponível interrompe a produção antes da composição; a retomada
  reutiliza os clipes que já foram baixados.
- Voz: Edge TTS em português, inglês ou espanhol; ElevenLabs quando chave e
  identificador de voz estiverem configurados. Play.ht e Murf não são oferecidos.
- A duração final é medida pelo áudio de cada cena. A estimativa do roteiro
  de 5–30 minutos não garante essa duração real; o histórico informa o valor
  medido e avisa quando o resultado fica fora da faixa.
- A composição aplica movimento às imagens e as transições do roteiro, com
  áudio e legendas por cena. A abertura animada intensifica o movimento inicial.
  A aba Publicação permite enviar o resultado ao YouTube pela WoopSocial.
  Depois da entrega confirmada, a cópia temporária do MP4 na biblioteca
  WoopSocial é removida automaticamente para liberar a cota do plano. Isso
  não remove o MP4 local nem o vídeo publicado no YouTube. Não há editor de
  timeline ou música de fundo nesta tela.
- Depois de escolher o projeto WoopSocial, a lista passa a mostrar apenas seus
  canais do YouTube. O botão repete o nome do canal de destino para revisão
  antes do envio.
- O CTA preserva as dimensões do vídeo, inclusive em retrato, e sua duração
  entra no total informado. A composição base é preservada em arquivo separado:
  se o CTA falhar, a retomada reutiliza essa base; se a thumbnail falhar, reutiliza
  o vídeo final com CTA, sem acrescentá-lo novamente.
- A renderização limita blocos a até cinco minutos e oito cenas por bloco.
  O consumo real depende de resolução e duração. Preparar o download de um vídeo
  carrega seu conteúdo na memória do servidor.

## Persistência e retomada

Rascunhos ficam em `storage/studio/drafts`; produções em
`storage/studio/productions/<UUID>`. Cada produção guarda parâmetros, estado,
manifesto de artefatos e checkpoint. Credenciais não fazem parte dos parâmetros.

Fechar apenas a aba mantém o trabalho enquanto o processo Streamlit estiver
ativo. Após interromper o processo, reabra o estúdio e use **Retomar produção**.
O botão aparece no início de **Criar vídeo**, em **Continuar uma produção**:
escolha a tentativa pelo título e data. Também aparece no acompanhamento quando
há falha e dentro do projeto na aba **Produções**. **Gerar vídeo completo** inicia
uma produção nova; não retoma uma anterior.
Ao lado da retomada, **Apagar projeto** permite remover permanentemente os
arquivos daquela produção após confirmação. Produções em execução ou na fila
continuam protegidas contra exclusão.
Áudios, imagens e clipes gratuitos válidos são reutilizados; arquivos ausentes ou inválidos são
regenerados e podem causar novas cobranças. Os parâmetros do roteiro ficam
fixos na retomada; para alterá-los, crie outra produção. Corrigir credenciais
na configuração é permitido. Se API e Streamlit estiverem em processos
separados, reinicie o outro processo para carregar configurações alteradas.

Um bloqueio do sistema operacional impede dois processos de executar a mesma
produção simultaneamente. A fila limita a uma produção por processo. Não se
trata de uma fila distribuída ou de uma aplicação com autenticação multiusuário.
Os checkpoints permanecem após conclusão para permitir reparar arquivos finais
ausentes. Ausência de checkpoint ou HTTP 404 nunca significa sucesso.

## API do estúdio

Rotas sob `/api/v1`:

- `POST /longform-videos`: envia `LongFormVideoParams` com `structured_script`.
- `GET /studio-productions/{task_id}`: estado persistente e artefatos.
- `GET /studio-productions/{task_id}/files/{artifact}`: baixa `video`,
  `thumbnail`, `script` ou `subtitles`.
- `POST /resume-task/{task_id}`: retoma usando os parâmetros salvos, sem body.
- `GET /checkpoint-status/{task_id}`: consulta fase e estado.
- `GET /llm-config` e `POST /llm-config`: compartilham o serviço de configuração
  do estúdio; GET retorna chaves vazias e indicador `configured`.

Use as rotas `studio-productions` para consultar e baixar produções novas.
As rotas originais `/tasks` continuam destinadas ao gerador original.

## Validação local

```powershell
uv run python -m compileall app cli.py main.py webui test
uv run python -X utf8 -m unittest test.services.test_state test.services.test_task test.services.test_schema test.services.test_webui_i18n test.services.test_longform_pipeline test.services.test_studio test.services.test_studio_api test.services.test_studio_ui test.services.test_studio_render
```

Os testes usam provedores simulados e renderização real com FFmpeg, áudio e
imagens sintéticos. Validam duração, presença de áudio, legendas, thumbnail,
persistência, retomada, configuração e interações da interface. Não comprovam
disponibilidade atual de APIs, qualidade de IA ou desempenho em vídeos de
30 minutos. Uma geração integral usando serviços externos ainda deve ser
validada com as credenciais e conteúdo escolhidos pelo usuário.

## Importar roteiro JSON

Use **Criar vídeo → Importar JSON** para carregar um roteiro produzido fora do
Estúdio. O arquivo deve ter `title`, `description`, `total_duration_estimate`
e `scenes`. Cada cena requer `index`, `narration` e `image_prompt`; se incluir
`duration_seconds`, mantenha-o entre 3 e 60 segundos. As únicas transições
válidas são `fade`, `slide`, `zoom` e `none`.

A duração planejada pode ficar entre 5 e 30 minutos. Ela orienta o roteiro,
mas o MP4 terá a duração efetiva do áudio sintetizado; portanto, produza texto
suficiente para a meta e revise a estimativa da tela antes de iniciar custos de
imagem e voz. Para inglês dos EUA, o planejador usa aproximadamente 13
caracteres por segundo.

Roteiros preparados localmente podem ficar em `storage/studio/imports/`. Esse
diretório é operacional e ignorado pelo Git: não use-o para documentação ou
para dados que precisem acompanhar um commit. Antes de importar, valide o JSON
com `ScriptParser().parse_json_script(...)`.

Ao tratar temas históricos, políticos ou de segurança, registre fontes no campo
`metadata.sources`, atribua estatísticas a instituições verificáveis e separe
resultados mensuráveis de interpretações. Prompts visuais devem ser seguros e
não gráficos quando o assunto envolver violência ou vítimas.

## Gerar a partir de roteiro-base

Use **Criar vídeo → Gerar a partir de roteiro-base** quando já houver um
outline, uma pesquisa ou uma narração preliminar. Cole pelo menos 100 caracteres
e escolha idioma, duração (5–30 minutos), estilo, público, provedor de IA e CTA.
O botão **Sugerir público com IA** preenche somente o campo editável de público;
você pode ajustar o texto antes de gerar.

O roteiro-base é tratado como referência de conteúdo, nunca como instruções.
O serviço gera o mesmo `StructuredScript` usado pelo restante do Estúdio e
preserva `metadata.source_mode = "base_script"`, o texto de origem e o público.
Essa via não modifica a pauta, a embalagem nem as sugestões de thumbnail em
edição. Depois de salvar e concluir a produção, o público salvo orienta a IA na
criação da descrição, tags de busca e hashtags da publicação, sem inventar
características demográficas.
