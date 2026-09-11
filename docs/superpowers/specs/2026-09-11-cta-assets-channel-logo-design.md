# CTA visual e logo por canal

## Objetivo

Permitir que cada canal tenha uma logo persistente e um CTA padrão configurável
como texto, imagem ou vídeo. O vídeo deve guardar uma cópia dos ativos escolhidos
para que possa ser reproduzido ou retomado mesmo se o perfil do canal mudar.

## Decisão

O perfil do canal terá estes campos adicionais:

- `logo_path`: logo PNG, JPG ou WebP do canal.
- `cta_mode`: `text`, `image` ou `video`.
- `cta_asset_path`: imagem ou vídeo do CTA, quando aplicável.
- `default_cta`: texto editável da chamada.

Os ativos do perfil ficarão em `storage/studio/channel_assets/<canal>/`. O
cadastro continuará sendo JSON; os caminhos salvos serão locais e relativos à
área do Estúdio. Um perfil antigo sem esses campos continua válido e usa CTA de
texto sem logo.

## Interface

Na identidade editorial haverá um upload de logo, prévia e ação para substituir
o arquivo. A configuração de CTA exibirá o texto e o seletor de formato:

- **Texto:** usa logo do canal centralizada e o texto abaixo.
- **Imagem:** pede uma imagem de CTA e mostra prévia.
- **Vídeo:** pede um MP4, MOV ou WebM de CTA e mostra o nome do arquivo.

Na geração de roteiro, o CTA do canal continua sugerido e editável para aquele
vídeo. O modo e o ativo padrão também acompanham o roteiro; o usuário pode
substituir o formato e o ativo somente naquele vídeo. O texto ainda orienta a
narração da cena CTA, qualquer que seja o visual escolhido.

## Renderização

Depois da última cena narrada, o pipeline acrescenta uma endcard:

- Texto: fundo sóbrio, logo centralizada e texto centralizado abaixo por cinco
  segundos.
- Imagem: a imagem é ajustada para a proporção final e exibida por cinco
  segundos.
- Vídeo: o arquivo é ajustado para a proporção final e reproduzido por até
  quinze segundos; seu áudio é mantido quando existir.

A endcard não substitui a narração da cena CTA; ela cria uma conclusão visual
clara. Cada produção recebe cópias de `logo` e do ativo de CTA dentro de sua
pasta antes de iniciar o pipeline. A composição usa essas cópias, preservando
retomadas e projetos concluídos.

## Validação e erros

Logo e imagem aceitam PNG, JPG e WebP. Vídeo aceita MP4, MOV e WebM. Arquivos
ausentes, inválidos ou sem quadro/vídeo legível impedem a produção antes de
gerar mídia paga e informam o campo que precisa ser corrigido. Se o CTA for de
texto e não houver logo, o vídeo mantém o texto centralizado sem falhar.

## Testes

- Perfil salva e recupera os caminhos de logo e CTA.
- Produção copia os ativos para a sua própria pasta.
- CTA de texto produz endcard com logo acima do texto.
- CTA de imagem produz endcard na proporção de saída.
- CTA de vídeo é anexado com duração limitada e mantém áudio quando fornecido.
- Perfis e projetos antigos continuam produzindo sem ativos.

## Limites de escopo

Esta etapa não cria logos por IA nem adiciona animação a arquivos estáticos de
CTA. A abertura animada e as transições de cenas continuam independentes da
endcard.
