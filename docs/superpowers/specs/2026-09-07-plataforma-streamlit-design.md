# Plataforma de geração completa no Streamlit

Status: proposta para revisão do usuário. Escolha confirmada: evoluir o Streamlit existente.

## Resultado esperado

Operar pelo navegador, em português brasileiro, desde a configuração dos provedores até a prévia e o download do vídeo com narração, imagens, legendas opcionais e thumbnail. Preservar o modo original de vídeos curtos. Uso local individual nesta primeira entrega.

## Abordagens avaliadas

1. Página dedicada de vídeos longos no Streamlit, com módulos próprios e serviços compartilhados: recomendada por preservar o fluxo original e separar responsabilidades.
2. Acrescentar todos os controles ao formulário atual: menor mudança inicial, mas amplia um arquivo já extenso e mistura dois fluxos distintos.
3. Streamlit como cliente exclusivo da API: separa processos, mas exige operar dois servidores. Não é necessário para o uso local inicial.

## Experiência proposta

- Navegação entre vídeos curtos, criação de vídeo longo, produções e configurações.
- Configurações: provedor/modelo de roteiro, imagens e voz; campos de senha para credenciais; edição sem substituir chaves por valores mascarados. Mostrar somente opções implementadas e validar configurações antes de gerar.
- Novo vídeo: tema, idioma, duração desejada de 15–30 minutos, estilo e público. Gerar roteiro ou importar JSON.
- Revisão: editar título, descrição, narração e prompt visual por cena; adicionar/remover cenas respeitando o contrato; salvar rascunho e exportar roteiro.
- Produção: selecionar voz, formato, legendas, aparência e texto da thumbnail. Um botão inicia as etapas restantes após revisão do roteiro.
- Acompanhamento: fila, etapa atual, progresso e erro compreensível, sem bloquear a navegação. Atualizações do navegador não devem iniciar tarefas duplicadas.
- Produções: histórico persistente, retomada de falhas com parâmetros salvos, prévia do vídeo e thumbnail, download dos artefatos existentes.
- Publicação automática no YouTube não integra esta entrega; o resultado é o material pronto para publicação.

## Backend necessário

Reutilizar a fila existente e os serviços Python, sem depender de um segundo servidor para o Streamlit. Isolar a interface long-form em módulos próprios. Persistir rascunhos, parâmetros sem credenciais, estado e caminhos de artefatos por produção; usar checkpoints para retomada e verificar os arquivos antes de reaproveitá-los.

Corrigir imports incompatíveis com MoviePy 2, resolução do FFmpeg e falhas de composição. Preservar o vínculo entre cenas e narração durante geração e retomada. Usar duração medida do áudio na composição; apresentar duração estimada e real separadamente, sem declarar 15–30 minutos apenas pelo campo do roteiro. Implementar geração e aplicação efetiva de legendas quando habilitadas. Não aceitar vídeo parcial como sucesso quando faltarem cenas, áudio ou blocos.

Executar thumbnail no fluxo completo e não marcar conclusão integral quando ela falhar. Corrigir substituição do checkpoint, restauração das chaves de índices de imagem após JSON e persistência dos parâmetros para retomada. Respeitar habilitação de checkpoints. Separar estado de tarefa de existência de checkpoint.

Conectar configuração de imagens e voz à seleção efetiva dos serviços. Manter os seis provedores de roteiro existentes; não anunciar Midjourney, Play.ht ou Murf como disponíveis enquanto não houver implementação. APIs e geração pagas dependem das credenciais do usuário e da ação explícita de gerar.

## Verificação

Testes determinísticos para configurações, validação, fila sem duplicação, persistência, retomada, falhas parciais e conclusão com thumbnail. Testar vínculo cena/áudio, duração, legendas e composição com artefatos sintéticos locais. Verificar a interface com testes Streamlit e navegação no navegador quando disponível. Executar a seleção atual do CI para detectar regressões. Chamadas reais a provedores não são substituídas por mocks como evidência de integração externa.

## Sequência

1. Corrigir e testar o fluxo completo e a retomada.
2. Integrar configurações, editor de roteiro e geração no Streamlit.
3. Integrar histórico, progresso, prévias e downloads.
4. Verificar o percurso completo com mídia local e documentar inicialização e limitações comprovadas.
