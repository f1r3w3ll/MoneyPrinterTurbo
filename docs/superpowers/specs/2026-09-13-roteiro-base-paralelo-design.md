# Roteiro-base como origem paralela de roteiro

## Objetivo

Adicionar uma segunda forma de criar um roteiro estruturado no Estúdio. O usuário cola um roteiro-base completo, informa idioma, duração, estilo, público e provedor de IA, e recebe um `StructuredScript` compatível com o MoneyPrinter. A origem atual por pauta continua inalterada.

## Experiência

Em **Criar vídeo → 3 · Prepare o roteiro**, haverá um expansor independente chamado **Gerar a partir de roteiro-base** ao lado das opções atuais de gerar por pauta/IA, importar JSON e criar rascunho.

O formulário terá:

- campo obrigatório para colar o roteiro-base;
- seletor de idioma, duração de 5 a 30 minutos, estilo e provedor;
- campo de público-alvo com botão para a IA sugerir uma proposta editável;
- opção de CTA já existente, sem alterar a configuração de CTA do canal.

Ao enviar, a IA transforma a fonte em cenas, preserva a linha narrativa e os fatos apresentados, preenche prompts visuais seguros em inglês e usa o orçamento de duração do gerador. A geração não altera pauta, embalagem ou thumbnail atuais. O editor de cenas continua sendo a etapa obrigatória de revisão antes da produção.

## Dados e contratos

O serviço receberá uma solicitação explícita de geração a partir de fonte, em vez de tratar o roteiro-base como orientação genérica. Ele instruirá o modelo a tratar o texto colado como material de referência, nunca como instruções de sistema.

Os metadados do JSON resultante registrarão `source_mode: "base_script"`, idioma, duração, público, estilo, provedor e o texto-base. Isso permite abrir uma produção posterior com seu contexto editorial. O texto não pode conter credenciais; a interface exibirá aviso para não colar informações privadas.

## Público e publicação

O botão de sugestão retorna somente um público-alvo conciso, sempre editável. Esse público é incluído nos metadados do roteiro e na solicitação de descrição do YouTube. A geração de hashtags e tags deverá usá-lo como contexto, sem inventar características demográficas nem substituir os temas do vídeo.

## Erros e validação

Campos vazios, provider não configurado, JSON inválido do modelo e um roteiro fora do contrato seguem o tratamento de erro já usado para geração por pauta. O resultado deve passar por `ScriptParser` antes de entrar no editor. A origem de pauta, a importação JSON e o rascunho manual terão testes de regressão para garantir que continuam disponíveis.

## Verificação

Testes cobrirão a montagem da instrução para roteiro-base, os metadados persistidos, a sugestão editável de público, o contexto de público na publicação e a renderização da nova opção sem alterar as opções existentes. Nenhuma alteração exige reiniciar a aplicação antes do fim da produção atual.

## Fora de escopo nesta etapa

A publicação da thumbnail exige a API oficial do YouTube porque o contrato atual da WoopSocial não expõe esse campo. Ela será planejada separadamente, após definir o fluxo de autorização Google por canal.

## Diretriz editorial para o canal americano

O perfil ativo **No One Wrote It Down** atenderá adultos dos Estados Unidos entre
25 e 44 anos, curiosos e profissionalmente interessados em ciência, tecnologia,
infraestrutura e seus efeitos cotidianos. A linguagem da narração será inglês
americano claro e natural: abre com uma tensão concreta, explica termos técnicos
na primeira ocorrência e usa exemplos reconhecíveis no contexto dos Estados
Unidos sem presumir conhecimento especializado.

O tom será documentário explicativo, direto, inteligente e conversacional. Cada
vídeo deverá apoiar afirmações factuais em fontes primárias, instituições
científicas, documentação técnica ou jornalismo confiável; dados contestados
serão atribuídos e datados. Hashtags e tags usarão o tema, o público de 25–44 e
o benefício prático do vídeo, sem inventar interesses demográficos ou recorrer
a linguagem de choque.
