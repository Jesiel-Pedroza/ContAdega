# PWA e contagem offline

## Instalação

O primeiro preparo exige HTTPS (ou `localhost`), login e conexão. Abra uma contagem e toque em **Preparar para uso offline** antes de perder a rede.

- **Android (Chrome):** menu ⋮ → **Adicionar à tela inicial** / **Instalar app**.
- **iPhone (Safari):** botão Compartilhar → **Adicionar à Tela de Início**. No iOS, abra o atalho uma vez conectado antes do uso offline.

Cada pacote pertence ao usuário autenticado, inventário e etapa e expira em oito horas. Páginas privadas e respostas de API não são guardadas pelo service worker. A fila IndexedDB sobrevive ao fechamento, à falta de rede e à expiração da sessão. Um logout explícito remove apenas os dados daquele usuário. Conflitos permanecem registrados e nunca são resolvidos por “última gravação vence”.

## Homologação em celular real

Este roteiro deve ser executado em Android e iPhone reais; não foi executado automaticamente:

1. Instalar pelo navegador e confirmar que somente `icon.svg` é utilizado.
2. Entrar como contador, abrir uma posição, preparar o pacote e conferir a validade exibida.
3. Ativar modo avião, fechar e reabrir o app; retomar a posição e lançar com entrada manual, +1, −1, teclado numérico, confirmação e desfazer.
4. Ler o QR correto e um incorreto. Ler EAN e Code 128 quando `BarcodeDetector` estiver disponível; confirmar fallback manual quando não estiver.
5. Ligar/desligar a câmera, sair da tela e confirmar que o indicador da câmera apaga. Verificar no proxy/rede que nenhuma foto ou mídia foi enviada.
6. Criar pendências, encerrar a sessão no servidor e confirmar que elas permanecem. Autenticar novamente e sincronizar manualmente.
7. Em dois aparelhos, preparar a mesma versão, sincronizar o primeiro e depois o segundo; confirmar conflito preservado, sem sobrescrita.
8. Repetir após finalizar a posição e após cancelar/aprovar o inventário; confirmar rejeições individuais.
9. Fazer logout explícito e confirmar a limpeza dos dados desse usuário sem apagar dados pertencentes a outro usuário no aparelho.
10. Atualizar a aplicação e confirmar ativação do novo cache e remoção do cache `contadega-*` anterior.
