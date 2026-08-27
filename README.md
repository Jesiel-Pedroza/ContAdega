# ContAdega

Aplicação web independente, mobile-first, para cadastros, estoque esperado e inventário físico cego de vinhos em adegas. Inclui autenticação por perfis, PWA/offline, etiquetas com QR, relatórios e CSV, duas contagens, auditoria, backup SQLite consistente e aprovação transacional.

## Requisitos

- Python 3.11 ou superior e `pip`;
- SQLite 3 (incluído no Python);
- navegador moderno. Não há dependências de CDN.

## Instalação

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuração e execução

Defina uma chave longa e aleatória. Em Linux: `export SECRET_KEY="..."`; no PowerShell: `$env:SECRET_KEY="..."`. Opcionalmente, `DATABASE_URL=sqlite:////caminho/contadega.sqlite` troca o banco e `COOKIE_SECURE=true` exige HTTPS.

O esquema **não é criado automaticamente** na inicialização:

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app run --host 0.0.0.0
```

Acesse `http://127.0.0.1:5000`. Sem usuários, a aplicação direciona para a criação única do primeiro administrador. Datas são exibidas em `America/Sao_Paulo`.

## Testes

```bash
pytest -q
```

Os testes usam bancos temporários e desabilitam CSRF apenas nas fixtures que exercitam regras funcionais; há um teste separado com CSRF ativo.

## Estrutura

- `contadega/__init__.py`: application factory, SQLite e tratamento de erros;
- `contadega/config.py` e `extensions.py`: configuração e extensões;
- `contadega/models.py`: modelos e restrições relacionais;
- `contadega/services.py`: validação, regras e importação transacional;
- `contadega/routes.py`: Blueprint, sessão e autorização;
- `contadega/templates` e `contadega/static`: Jinja2, CSS e JavaScript próprios;
- `migrations`: histórico Alembic desde a primeira versão;
- `tests`: testes de segurança, cadastros, restrições e CSV.

## Estoque e inventário

Administradores mantêm o estoque esperado em **Estoque**, com consulta por vinho ou posição, importação/exportação CSV e histórico que distingue ajustes administrativos de aplicações de inventário. Em **Inventários**, o administrador define a adega e posições, inicia o snapshot imutável, acompanha o progresso e aprova com ou sem aplicação do físico.

A primeira contagem e a conferência são cegas. Cada posição é bloqueada por sessão, usa versão otimista contra submissões concorrentes e permanece editável somente até sua finalização. Divergências seguem para recontagem com justificativa. Inventários aprovados ou cancelados são imutáveis.

## SQLite, concorrência e backup

As conexões ativam `foreign_keys`, WAL e `busy_timeout=5000`. WAL melhora leituras simultâneas, mas SQLite continua permitindo apenas um escritor por vez; para muitos dispositivos escrevendo ao mesmo tempo, migre futuramente para um SGBD servidor.

Administradores podem criar um backup consistente e verificado em **Manutenção**. A rotina usa a API de backup do SQLite, não uma cópia simples do arquivo ativo. `BACKUP_DIRECTORY` define o diretório (padrão `instance/backups`) e `BACKUP_RETENTION` a quantidade retida (padrão 14). A interface não baixa nem restaura backups. Veja o procedimento deliberado de restauração em [MANUAL_OPERACIONAL.md](MANUAL_OPERACIONAL.md).

## Relatórios, manutenção e demonstração

**Relatórios** oferece dez visões operacionais, filtros, CSV UTF-8 com BOM e separador `;`, além de impressão HTML. **Etiquetas** gera folhas A4 em três tamanhos; o QR contém apenas o UUID público da posição. **Manutenção** mostra integridade e tamanhos do SQLite e dos backups. A trilha de auditoria é somente leitura na interface.

Dados fictícios nunca são carregados automaticamente. Em um banco vazio, execute separadamente:

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app demo-data
```

O fluxo diário completo, PWA, backup, restauração e solução de problemas estão no [manual operacional](MANUAL_OPERACIONAL.md).

## Segurança operacional

Use HTTPS e `COOKIE_SECURE=true` fora de uma rede local controlada. Não versione `.env`, banco ou backups. O limitador de login é propositalmente em memória no MVP: reinicia com o processo e não é compartilhado entre múltiplos workers.
