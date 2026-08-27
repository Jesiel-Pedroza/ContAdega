# Manual operacional do ContAdega

## Preparação e cadastro

1. Mapeie a adega, nomeie setores e defina códigos únicos e legíveis para todas as posições.
2. Como administrador, cadastre **Adegas**, **Setores** e **Posições**. Informe descrição e capacidade quando conhecidas.
3. Em **Etiquetas**, selecione as posições, escolha o tamanho, gere a folha A4 e confira a pré-visualização antes de imprimir. Coloque cada etiqueta na posição correspondente; o QR contém somente o identificador aleatório da posição.
4. Cadastre os vinhos manualmente ou use o modelo em **Vinhos > Importar CSV**. Arquivos devem ser UTF-8, ter até 2 MiB e usar o cabeçalho documentado. Revise a prévia antes de confirmar.
5. Em **Estoque**, associe posição, vinho e quantidade esperada. Registre uma justificativa para cada ajuste ou importe `posicao_id;vinho_id;quantidade`.

## Inventário completo

1. Crie um inventário, escolha uma única adega e suas posições. Inicie-o para congelar o estoque esperado em um snapshot.
2. O contador abre cada posição (ou lê seu QR), registra a primeira contagem cega e a finaliza.
3. Avance para conferência. Um usuário diferente realiza a segunda contagem, também cega.
4. Consulte **Relatórios > Divergências**. Recontagens exigem justificativa; resolva também itens ausentes, excedentes e encontrados no local incorreto.
5. Avance para aprovação. Somente administrador pode aprovar e decidir deliberadamente se o físico será aplicado ao estoque esperado.
6. Exporte o relatório em CSV UTF-8 com BOM e `;`, adequado ao Excel em português do Brasil, ou use a visualização de impressão.

## PWA e operação offline

Instale pelo menu do navegador. Antes de perder conexão, abra a posição e selecione **Preparar para uso offline**. As operações ficam apenas no IndexedDB daquele usuário e dispositivo, são sincronizadas em ordem e conflitos nunca sobrescrevem silenciosamente o servidor. Não limpe os dados do navegador com fila pendente. Consulte `PWA_OFFLINE.md` para detalhes.

## Backup diário e restauração

Em **Manutenção**, execute diariamente **Criar e verificar backup consistente**. O sistema usa a API de backup online do SQLite, executa `PRAGMA integrity_check`, mantém por padrão os 14 arquivos mais recentes e informa o diretório absoluto. Restrinja esse diretório no sistema operacional; apenas administradores acessam a operação e a interface não oferece download.

Para restaurar: pare a aplicação; preserve uma cópia do banco ativo e arquivos auxiliares; verifique o backup em uma cópia (`sqlite3 arquivo.sqlite 'PRAGMA integrity_check;'`); configure `DATABASE_URL` para a cópia restaurada ou substitua o arquivo **manualmente e deliberadamente**; execute `flask --app wsgi:app db upgrade`; inicie a aplicação e valide login, estoque e último inventário. Nunca restaure sobre um processo ativo.

## Solução de problemas

- **Banco ocupado:** aguarde o escritor atual; verifique disco e permissões. O `busy_timeout` é de cinco segundos.
- **Conflito offline:** mantenha a fila, recarregue os dados online e refaça a operação após revisão.
- **QR ilegível:** reimprima em tamanho maior, sem redimensionar desproporcionalmente, e mantenha contraste.
- **CSV rejeitado:** confirme UTF-8, cabeçalho, extensão, limite de 2 MiB e valores inteiros não negativos.
- **Integridade diferente de `ok`:** interrompa gravações, preserve os arquivos e acione o responsável técnico antes de restaurar.
