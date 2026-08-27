import csv, io
from sqlalchemy import func
from .extensions import db
from .models import Cellar, Position, Role, Sector, User, Wine, now

ROLES=("administrador","contador","conferente")
def normalize(value): return (value or "").strip()
def create_first_admin(name, username, password, confirmation):
    if db.session.query(User.id).first(): raise ValueError("O primeiro acesso já foi concluído.")
    if len(password)<8: raise ValueError("A senha deve ter ao menos 8 caracteres.")
    if password != confirmation: raise ValueError("As senhas não coincidem.")
    if not normalize(name) or not normalize(username): raise ValueError("Preencha todos os campos.")
    role=Role.query.filter_by(name="administrador").first() or Role(name="administrador")
    user=User(name=normalize(name), username=normalize(username), roles=[role]); user.set_password(password); db.session.add(user); db.session.commit(); return user
def create_user(data):
    if User.query.filter(func.lower(User.username)==normalize(data.get("username")).lower()).first(): raise ValueError("Usuário já cadastrado.")
    if len(data.get("password", ""))<8: raise ValueError("A senha deve ter ao menos 8 caracteres.")
    roles=Role.query.filter(Role.name.in_(data.getlist("roles"))).all();
    if not roles: raise ValueError("Selecione ao menos um perfil.")
    user=User(name=normalize(data.get("name")),username=normalize(data.get("username")),roles=roles,active=data.get("active")=="on"); user.set_password(data["password"]); db.session.add(user); db.session.commit(); return user
def create_wine(data):
    barcode=normalize(data.get("barcode")) or None
    if barcode and Wine.query.filter_by(barcode=barcode).first(): raise ValueError("Código de barras já cadastrado.")
    try: volume=int(data.get("volume_ml",0)); vintage=int(data["vintage"]) if normalize(data.get("vintage")) else None
    except ValueError: raise ValueError("Safra e volume devem ser números.")
    if volume<=0 or not all(normalize(data.get(k)) for k in ("name","producer","country","type")): raise ValueError("Preencha os campos obrigatórios.")
    wine=Wine(name=normalize(data["name"]),producer=normalize(data["producer"]),country=normalize(data["country"]),region=normalize(data.get("region")),type=normalize(data["type"]),grape=normalize(data.get("grape")),vintage=vintage,volume_ml=volume,barcode=barcode,notes=normalize(data.get("notes"))); db.session.add(wine); db.session.commit(); return wine
def create_cellar(data):
    obj=Cellar(name=normalize(data.get("name")),description=normalize(data.get("description")));
    if not obj.name: raise ValueError("Informe o nome.")
    db.session.add(obj); db.session.commit(); return obj
def create_sector(data):
    obj=Sector(cellar_id=int(data["cellar_id"]),code=normalize(data["code"]).upper(),name=normalize(data["name"]),display_order=int(data.get("display_order",0)))
    if not obj.code or not obj.name: raise ValueError("Preencha os campos obrigatórios.")
    db.session.add(obj); db.session.commit(); return obj
def create_position(data):
    sector=db.session.get(Sector,int(data["sector_id"])); code=normalize(data["code"]).upper()
    exists=Position.query.join(Sector).filter(Sector.cellar_id==sector.cellar_id, func.lower(Position.code)==code.lower()).first()
    if exists: raise ValueError("Código de posição já existe nesta adega.")
    capacity=int(data["capacity"]) if normalize(data.get("capacity")) else None
    obj=Position(sector=sector,cellar_id=sector.cellar_id,code=code,description=normalize(data.get("description")),display_order=int(data.get("display_order",0)),capacity=capacity); db.session.add(obj); db.session.commit(); return obj

CSV_FIELDS=("nome","produtor","pais","regiao","tipo","uva","safra","volume_ml","codigo_barras","observacoes")
def parse_csv(raw):
    try: text=raw.decode("utf-8-sig")
    except UnicodeDecodeError: return [], ["O arquivo deve estar em UTF-8."]
    try: dialect=csv.Sniffer().sniff(text[:2048], delimiters=",;"); rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
    except csv.Error: return [], ["CSV inválido."]
    errors=[]; parsed=[]; seen=set()
    if not rows or not set(CSV_FIELDS).issubset(rows[0].keys()): return [], ["Cabeçalho inválido. Baixe o arquivo-modelo."]
    existing={x[0] for x in db.session.query(Wine.barcode).filter(Wine.barcode.isnot(None))}
    for no,row in enumerate(rows,2):
        barcode=normalize(row["codigo_barras"]) or None
        try: volume=int(row["volume_ml"]); vintage=int(row["safra"]) if normalize(row["safra"]) else None
        except ValueError: errors.append(f"Linha {no}: safra/volume inválido."); continue
        if not all(normalize(row[k]) for k in ("nome","produtor","pais","tipo")) or volume<=0: errors.append(f"Linha {no}: campos obrigatórios inválidos.")
        elif barcode and (barcode in seen or barcode in existing): errors.append(f"Linha {no}: código de barras duplicado.")
        else: seen.add(barcode); parsed.append(dict(name=normalize(row["nome"]),producer=normalize(row["produtor"]),country=normalize(row["pais"]),region=normalize(row["regiao"]),type=normalize(row["tipo"]),grape=normalize(row["uva"]),vintage=vintage,volume_ml=volume,barcode=barcode,notes=normalize(row["observacoes"])))
    return parsed,errors
def import_wines(rows):
    try: db.session.add_all(Wine(**row) for row in rows); db.session.commit()
    except Exception: db.session.rollback(); raise
