# Abertura animada, movimento cinematográfico e CTA configurável

## Objetivo

Aumentar a retenção do vídeo com uma abertura animada opcional, preservar custo
previsível com imagens estáticas animadas localmente no restante da produção e
permitir um CTA padrão por canal que continua editável antes da geração do
roteiro.

## Escopo aprovado

A interface de criação terá uma opção por vídeo, desativada por padrão, para
usar uma abertura animada. Quando marcada, as primeiras cenas do gancho serão
marcadas para geração de clipes curtos por IA. Fora dessa abertura, todas as
cenas continuam originadas de imagens, mas a composição aplica movimento de
câmera local e transições visíveis.

Configurações de canal incluirá um CTA padrão. A pauta/roteiro poderá optar por
usar esse texto; se optar, o gerador recebe o CTA como instrução e o roteiro
mostra a cena final para edição normal. O texto não é imposto: o usuário pode
desmarcar seu uso em qualquer vídeo ou editar a narração depois da geração.

## Decisões de produto

- Abertura animada é opt-in por produção e não altera vídeos existentes.
- A abertura deve usar apenas as primeiras cenas classificadas como gancho, com
  limite configurado internamente de três cenas. Cada clipe terá curta duração
  e será combinado com a imagem local quando a narração da cena durar mais que
  o clipe.
- O modo padrão aplica movimento local determinístico às imagens: zoom suave,
  deslocamento horizontal ou vertical e enquadramento proporcional. A escolha
  deve ser estável por índice de cena para que retomar uma produção mantenha o
  mesmo resultado.
- As transições aceitas pelo parser (`fade`, `slide`, `zoom`, `none`) devem ser
  renderizadas no Estúdio; hoje elas são preservadas no roteiro, mas a
  composição long-form cria frames estáticos.
- A geração de clipes não reutilizará o serviço de imagem como se ele já
  soubesse gerar vídeo. Haverá uma fronteira própria de serviço para solicitar,
  acompanhar e salvar clipes. O primeiro provider será configurável e a
  indisponibilidade dele interromperá somente a abertura animada com erro
  compreensível, sem iniciar a renderização parcial.
- O CTA padrão pertence ao perfil editorial do canal, acompanha seu idioma e
  deve ser preenchido para o canal inicial em inglês com uma formulação
  apropriada. Um perfil novo inicia vazio para evitar inserir texto inesperado.

## Fluxo de dados

```text
Canal (CTA padrão) -> Pauta (usar CTA?) -> prompt de roteiro -> roteiro editável
Pauta (abertura animada?) -> metadados do roteiro -> pipeline
Pipeline: áudio -> imagem por cena -> clipe para cenas de abertura marcadas
          -> composição com movimento/transições/legendas -> MP4
```

Os metadados editoriais guardam `use_animated_intro`, o CTA adotado naquele
roteiro e as cenas de abertura selecionadas. O checkpoint passa a guardar o
caminho do clipe, quando houver, de forma análoga aos caminhos de áudio e
imagem. Assim uma retomada não cobra nem gera novamente um clipe já concluído.

## Composição

A composição será separada em adaptadores de mídia pequenos:

- um adaptador de imagem cria um `VideoClip` animado por toda a duração da
  cena;
- um adaptador de clipe abre e enquadra um vídeo de abertura, limita-o à sua
  duração útil e combina o restante da cena com o movimento da imagem;
- um adaptador de transição aplica a transição declarada entre cenas sem reduzir
  o áudio ou produzir duração negativa;
- legendas continuam sobre a imagem/clipe final, nunca embutidas no ativo de
  origem.

O compositor deve sempre usar a duração do áudio como duração efetiva de cada
cena. Clipes curtos não devem ser esticados no tempo: são mostrados uma vez e
o trecho restante volta para a imagem animada correspondente.

## Interface e progresso

A opção de abertura animada fica próxima das opções de produção, com texto que
indica que ela cria clipes de IA apenas para o gancho. A produção mostra a fase
`Gerando abertura animada` e a cena atual; as fases existentes continuam
visíveis. A ausência de configuração de provider de vídeo bloqueia apenas uma
produção que tenha a opção marcada e indica onde configurar o provider.

O CTA padrão fica na identidade editorial em Configurações. A pauta mostra um
checkbox para aplicá-lo e um campo editável com o texto efetivo do vídeo. O
roteiro gerado inclui-o na cena CTA no idioma do vídeo; a revisão conserva a
possibilidade de editar ou apagar a cena.

## Erros e limites

- Uma abertura marcada sem provider/chave configurada falha antes de chamar
  voz, imagem ou renderização.
- A falha de uma cena de clipe deixa checkpoint e a produção em falha, com
  retomada segura da cena pendente.
- Arquivos de clipe, como imagens e áudios, são removidos ao excluir uma
  produção.
- O limite de três cenas impede uso acidental de vídeo IA em toda a produção.

## Testes

Testes unitários devem verificar: metadados de CTA e abertura; inclusão do CTA
no prompt; seleção limitada das cenas de gancho; movimento local que muda o
frame ao longo do tempo; transições; uso do clipe seguido de imagem quando o
áudio é maior; retomada que não regenera clipe existente; e mensagens de
configuração ausente. Os testes de renderização usarão mídia curta criada
localmente e mocks de provider, sem chamadas pagas.
