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
2. Em **Criar vídeo**, gere um roteiro com IA, importe JSON ou crie um roteiro
   manual. A geração por IA oferece os seis provedores já integrados ao projeto.
3. Edite título, descrição, narração e descrição de imagem de cada cena.
   Use **Salvar roteiro** antes de produzir. É possível adicionar/remover cenas,
   exportar JSON e reabrir rascunhos salvos.
4. Escolha imagem, voz, formato, legendas e estilo da thumbnail. Clique em
   **Gerar vídeo completo**. Chamadas externas podem consumir créditos.
5. Em **Produções**, acompanhe as etapas. Use **Atualizar histórico** para
   carregar o resultado final, abrir o player e baixar MP4, thumbnail, roteiro
   e SRT quando as legendas estiverem habilitadas.

## Serviços e duração

- Imagens: DALL-E/OpenAI ou Stable Diffusion via Replicate. Midjourney não é
  oferecido porque sua implementação ainda não existe.
- Voz: Edge TTS em português, inglês ou espanhol; ElevenLabs quando chave e
  identificador de voz estiverem configurados. Play.ht e Murf não são oferecidos.
- A duração final é medida pelo áudio de cada cena. A estimativa do roteiro
  de 15–30 minutos não garante essa duração real; o histórico informa o valor
  medido e avisa quando o resultado fica fora da faixa.
- A composição usa imagens estáticas e cortes, com áudio e legendas por cena.
  Não há editor de timeline, publicação no YouTube ou música de fundo nesta tela.
- A renderização limita blocos a até cinco minutos e oito cenas por bloco.
  O consumo real depende de resolução e duração. Preparar o download de um vídeo
  carrega seu conteúdo na memória do servidor.

## Persistência e retomada

Rascunhos ficam em `storage/studio/drafts`; produções em
`storage/studio/productions/<UUID>`. Cada produção guarda parâmetros, estado,
manifesto de artefatos e checkpoint. Credenciais não fazem parte dos parâmetros.

Fechar apenas a aba mantém o trabalho enquanto o processo Streamlit estiver
ativo. Após interromper o processo, reabra o estúdio e use **Retomar produção**.
Áudios e imagens válidos são reutilizados; arquivos ausentes ou inválidos são
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
