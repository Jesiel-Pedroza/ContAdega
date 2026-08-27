# ContAdega

Aplicação web independente, mobile-first, para preparar cadastros e a conferência física de vinhos em adegas. Esta primeira etapa inclui autenticação, perfis, cadastros, QR Codes e importação CSV; inventário, PWA/offline e reconhecimento de imagem ficam fora do escopo atual.

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

## SQLite, concorrência e backup

As conexões ativam `foreign_keys`, WAL e `busy_timeout=5000`. WAL melhora leituras simultâneas, mas SQLite continua permitindo apenas um escritor por vez; para muitos dispositivos escrevendo ao mesmo tempo, migre futuramente para um SGBD servidor.

Para backup consistente, pare a aplicação e copie o arquivo `instance/contadega.sqlite` (e, caso existam, seus arquivos `-wal` e `-shm`) para mídia protegida. Alternativamente, com a aplicação parada: `sqlite3 instance/contadega.sqlite ".backup backup-contadega.sqlite"`. Teste periodicamente a restauração e proteja o backup, pois contém dados de usuários.

## Segurança operacional

Use HTTPS e `COOKIE_SECURE=true` fora de uma rede local controlada. Não versione `.env`, banco ou backups. O limitador de login é propositalmente em memória no MVP: reinicia com o processo e não é compartilhado entre múltiplos workers.
