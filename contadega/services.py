import csv, io
from sqlalchemy import func
from .extensions import db
from .models import (Cellar, ExpectedStock, Inventory, InventoryCount,
 InventoryScope, InventorySnapshot, Position, Role, Sector, StockHistory,
 User, Wine, now)

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

INVENTORY_TRANSITIONS={
 "rascunho":{"em_contagem","cancelado"}, "em_contagem":{"aguardando_conferencia","cancelado"},
 "aguardando_conferencia":{"em_conferencia","cancelado"},
 "em_conferencia":{"com_divergencias","aguardando_aprovacao","cancelado"},
 "com_divergencias":{"aguardando_aprovacao","cancelado"},
 "aguardando_aprovacao":{"aprovado","cancelado"}, "aprovado":set(), "cancelado":set()}

def transition_inventory(inventory,status):
    if status not in INVENTORY_TRANSITIONS.get(inventory.status,set()): raise ValueError("Transição de inventário inválida.")
    inventory.status=status
    if status=="em_contagem": inventory.started_at=now()
    if status=="aguardando_aprovacao": inventory.completed_at=now()

def adjust_stock(position,wine,quantity,user,reason,kind="administrativa",commit=True):
    quantity=int(quantity)
    if quantity<0: raise ValueError("A quantidade não pode ser negativa.")
    if not position.active or not wine.active: raise ValueError("Posição e vinho precisam estar ativos.")
    stock=ExpectedStock.query.filter_by(position_id=position.id,wine_id=wine.id).first()
    before=stock.quantity if stock else 0
    if stock is None:
        stock=ExpectedStock(cellar_id=position.cellar_id,position_id=position.id,wine_id=wine.id,quantity=quantity,updated_by_id=user.id); db.session.add(stock); db.session.flush()
    else: stock.quantity=quantity; stock.updated_by_id=user.id; stock.updated_at=now()
    db.session.add(StockHistory(stock_id=stock.id,cellar_id=position.cellar_id,position_id=position.id,wine_id=wine.id,quantity_before=before,quantity_after=quantity,kind=kind,reason=normalize(reason) or "Ajuste informado",user_id=user.id))
    if commit: db.session.commit()
    return stock

def create_inventory(name,cellar,positions,user,notes=""):
    if not name or not positions: raise ValueError("Informe nome e ao menos uma posição.")
    if any(p.cellar_id!=cellar.id or not p.active for p in positions): raise ValueError("Escopo contém posição inválida.")
    inv=Inventory(name=normalize(name),cellar_id=cellar.id,created_by_id=user.id,notes=normalize(notes)); db.session.add(inv); db.session.flush()
    for p in positions: db.session.add(InventoryScope(inventory_id=inv.id,position_id=p.id))
    db.session.commit(); return inv

def start_inventory(inv):
    transition_inventory(inv,"em_contagem")
    for scope in inv.scopes:
        for stock in ExpectedStock.query.filter_by(position_id=scope.position_id).all():
            db.session.add(InventorySnapshot(scope_id=scope.id,wine_id=stock.wine_id,quantity=stock.quantity))
    db.session.commit()

def save_count(inv,scope,wine,quantity,user,stage,version,device=None,observation=""):
    if inv.status in {"aprovado","cancelado"}: raise ValueError("Inventário encerrado não pode ser alterado.")
    valid={"primeira":"em_contagem","segunda":"em_conferencia","recontagem":"com_divergencias"}
    if valid.get(stage)!=inv.status: raise ValueError("Etapa de contagem inválida.")
    finished=getattr(scope,{"primeira":"first_finished_at","segunda":"second_finished_at","recontagem":"recount_finished_at"}[stage])
    if finished: raise ValueError("Posição já finalizada nesta etapa.")
    if int(version)!=scope.version: raise ValueError("A posição foi alterada em outra sessão. Atualize a página.")
    quantity=int(quantity)
    if quantity<0: raise ValueError("A quantidade não pode ser negativa.")
    count=InventoryCount.query.filter_by(inventory_id=inv.id,position_id=scope.position_id,wine_id=wine.id,stage=stage).first()
    if count: count.quantity=quantity; count.user_id=user.id; count.version+=1; count.counted_at=now(); count.observation=normalize(observation)
    else: db.session.add(InventoryCount(inventory_id=inv.id,position_id=scope.position_id,wine_id=wine.id,stage=stage,quantity=quantity,user_id=user.id,device=normalize(device),observation=normalize(observation)))
    scope.version+=1; db.session.commit()

def finish_position(inv,scope,user,stage,justification=""):
    attr={"primeira":"first_finished_at","segunda":"second_finished_at","recontagem":"recount_finished_at"}[stage]
    if getattr(scope,attr): raise ValueError("Posição já finalizada nesta etapa.")
    if stage=="segunda" and scope.first_user_id==user.id: raise ValueError("A conferência deve ser feita por outro usuário.")
    if stage=="recontagem" and not normalize(justification): raise ValueError("Informe a justificativa da recontagem.")
    setattr(scope,attr,now())
    if stage=="primeira": scope.first_user_id=user.id
    scope.lock_token=None; scope.lock_user_id=None; scope.version+=1; db.session.commit()

def acquire_position(scope,user,token):
    if scope.lock_token and scope.lock_token!=token: raise ValueError("Posição em contagem por outra sessão.")
    scope.lock_token=token; scope.lock_user_id=user.id; db.session.commit()

def count_map(inv,stage):
    return {(c.position_id,c.wine_id):c.quantity for c in inv.counts if c.stage==stage}

def classify_inventory(inv,stage="recontagem"):
    first=count_map(inv,"primeira"); selected=count_map(inv,stage) or count_map(inv,"segunda") or first
    expected={(s.position_id,x.wine_id):x.quantity for s in inv.scopes for x in s.snapshots}; keys=set(expected)|set(selected)
    result=[]
    total_e={}; total_f={}
    for (p,w),q in expected.items(): total_e[w]=total_e.get(w,0)+q
    for (p,w),q in selected.items(): total_f[w]=total_f.get(w,0)+q
    for p,w in sorted(keys):
        e,f=expected.get((p,w),0),selected.get((p,w),0)
        if (p,w) in first and (p,w) in count_map(inv,"segunda") and first[p,w]!=count_map(inv,"segunda")[p,w]: kind="divergencia de conferência"
        elif e==f: kind="correto"
        elif not e and f and total_e.get(w,0)==0: kind="produto inesperado"
        elif e!=f and total_e.get(w)==total_f.get(w): kind="local incorreto"
        elif e and not f: kind="não encontrado"
        elif f<e: kind="falta"
        else: kind="sobra"
        result.append({"position_id":p,"wine_id":w,"expected":e,"found":f,"classification":kind})
    return result

def approve_inventory(inv,user,apply_stock,justification):
    if not user.has_role("administrador"): raise PermissionError("Somente administrador pode aprovar.")
    if inv.status!="aguardando_aprovacao": raise ValueError("Inventário não está aguardando aprovação.")
    if not normalize(justification): raise ValueError("Confirmação e justificativa são obrigatórias.")
    try:
        if apply_stock:
            physical=count_map(inv,"recontagem") or count_map(inv,"segunda") or count_map(inv,"primeira")
            for scope in inv.scopes:
                wine_ids={x.wine_id for x in scope.snapshots}|{w for p,w in physical if p==scope.position_id}
                for wine_id in wine_ids: adjust_stock(scope.position,db.session.get(Wine,wine_id),physical.get((scope.position_id,wine_id),0),user,justification,"inventario",False)
        transition_inventory(inv,"aprovado"); inv.approved_at=now(); inv.approved_by_id=user.id; db.session.commit()
    except Exception: db.session.rollback(); raise
