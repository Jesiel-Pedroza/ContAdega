import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import current_app
from sqlalchemy import func
from .extensions import db
from .models import (AuditLog, ExpectedStock, Inventory, InventoryCount, InventoryScope,
                     OfflineOperation, Position, StockHistory, User, Wine)
from .services import classify_inventory

REPORT_TYPES={
    "geral":"Resultado geral do inventário", "vinhos":"Estoque físico por vinho",
    "posicoes":"Estoque físico por posição", "divergencias":"Divergências",
    "incorretos":"Vinhos em local incorreto", "pendentes":"Posições não contadas",
    "contagens":"Histórico de contagens e recontagens", "ajustes":"Ajustes aplicados",
    "auditoria":"Auditoria de ações", "comparacao":"Comparação entre inventários",
}

def audit(action,user=None,entity=None,detail=None):
    log=AuditLog(user_id=getattr(user,"id",None),action=action,
        entity_type=entity.__class__.__name__ if entity else None,
        entity_id=str(entity.id) if entity and getattr(entity,"id",None) is not None else None,
        detail=json.dumps(detail,ensure_ascii=False,default=str) if isinstance(detail,(dict,list)) else detail)
    db.session.add(log)
    return log

def filtered_report(kind,args):
    inventory_id=args.get("inventory_id",type=int); inv=db.session.get(Inventory,inventory_id) if inventory_id else None
    rows=[]
    if kind in {"geral","divergencias","incorretos","comparacao"}:
        inventories=[inv] if inv else Inventory.query.order_by(Inventory.id.desc()).all()
        compare_id=args.get("compare_id",type=int)
        if kind=="comparacao" and compare_id: inventories=[x for x in [inv,db.session.get(Inventory,compare_id)] if x]
        for item in inventories:
            for r in classify_inventory(item):
                position=db.session.get(Position,r["position_id"]); wine=db.session.get(Wine,r["wine_id"])
                row={"inventario":item.name,"adega":item.cellar.name,"setor":position.sector.name,"posicao":position.code,"vinho":wine.name,"produtor":wine.producer,"safra":wine.vintage or "","esperado":r["expected"],"fisico":r["found"],"divergencia":r["classification"]}
                if kind=="divergencias" and r["classification"]=="correto": continue
                if kind=="incorretos" and r["classification"]!="local incorreto": continue
                rows.append(row)
    elif kind in {"vinhos","posicoes"}:
        query=ExpectedStock.query.join(Position).join(Wine)
        for x in query.all(): rows.append({"adega":x.position.sector.cellar.name,"setor":x.position.sector.name,"posicao":x.position.code,"vinho":x.wine.name,"produtor":x.wine.producer,"safra":x.wine.vintage or "","quantidade":x.quantity})
    elif kind=="pendentes":
        query=InventoryScope.query.join(Inventory).join(Position)
        if inv: query=query.filter(InventoryScope.inventory_id==inv.id)
        for x in query.filter(InventoryScope.first_finished_at.is_(None)): rows.append({"inventario":x.inventory.name,"adega":x.inventory.cellar.name,"setor":x.position.sector.name,"posicao":x.position.code,"status":"pendente"})
    elif kind=="contagens":
        query=InventoryCount.query.join(Inventory).join(Position).join(Wine).join(User)
        if inv: query=query.filter(InventoryCount.inventory_id==inv.id)
        for x in query.order_by(InventoryCount.counted_at.desc()).all(): rows.append({"inventario":x.inventory_id,"posicao":x.position.code,"vinho":x.wine.name,"etapa":x.stage,"quantidade":x.quantity,"usuario":x.user.name,"data_hora":x.counted_at})
    elif kind=="ajustes":
        for x in StockHistory.query.order_by(StockHistory.created_at.desc()).all(): rows.append({"posicao":x.position_id,"vinho":x.wine_id,"antes":x.quantity_before,"depois":x.quantity_after,"tipo":x.kind,"motivo":x.reason,"usuario":x.user_id,"data_hora":x.created_at})
    elif kind=="auditoria":
        for x in AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5000): rows.append({"acao":x.action,"entidade":x.entity_type or "","identificador":x.entity_id or "","usuario":x.user.name if x.user else "sistema","data_hora":x.created_at,"detalhe":x.detail or ""})
    return apply_filters(rows,args)

def apply_filters(rows,args):
    aliases={"cellar":"adega","sector":"setor","position":"posicao","wine":"vinho","producer":"produtor","vintage":"safra","divergence":"divergencia","user":"usuario"}
    for source,key in aliases.items():
        value=(args.get(source) or "").strip().casefold()
        if value: rows=[r for r in rows if value in str(r.get(key,"")).casefold()]
    start=args.get("start"); end=args.get("end")
    if start: rows=[r for r in rows if str(r.get("data_hora",""))[:10]>=start]
    if end: rows=[r for r in rows if str(r.get("data_hora",""))[:10]<=end]
    return rows

def csv_bytes(rows,delimiter=";"):
    output=io.StringIO(newline=""); fields=list(rows[0]) if rows else ["resultado"]
    writer=csv.DictWriter(output,fieldnames=fields,delimiter=delimiter,lineterminator="\r\n"); writer.writeheader()
    for row in rows: writer.writerow({k:v.strftime("%d/%m/%Y %H:%M") if hasattr(v,"strftime") else v for k,v in row.items()})
    return output.getvalue().encode("utf-8-sig")

def sqlite_path():
    engine=db.engine
    if engine.url.get_backend_name()!="sqlite" or not engine.url.database: raise ValueError("A manutenção requer um banco SQLite em arquivo.")
    return Path(engine.url.database).resolve()

def create_backup():
    source=sqlite_path(); folder=Path(current_app.config["BACKUP_DIRECTORY"])
    if not folder.is_absolute(): folder=Path(current_app.instance_path)/folder
    folder.mkdir(parents=True,exist_ok=True); target=folder/f"contadega-{datetime.now():%Y%m%d-%H%M%S}.sqlite"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst: src.backup(dst)
    with sqlite3.connect(target) as check:
        if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok": target.unlink(missing_ok=True); raise RuntimeError("A verificação do backup falhou.")
    files=sorted(folder.glob("contadega-*.sqlite"),reverse=True)
    for old in files[current_app.config["BACKUP_RETENTION"]:]: old.unlink()
    return target

def maintenance_info():
    path=sqlite_path(); folder=Path(current_app.config["BACKUP_DIRECTORY"]); folder=folder if folder.is_absolute() else Path(current_app.instance_path)/folder
    with sqlite3.connect(path) as conn: integrity=conn.execute("PRAGMA integrity_check").fetchone()[0]
    backups=list(folder.glob("contadega-*.sqlite")) if folder.exists() else []
    return {"integridade":integrity,"banco":str(path),"tamanho_banco":path.stat().st_size,"diretorio_backups":str(folder.resolve()),"quantidade_backups":len(backups),"tamanho_backups":sum(x.stat().st_size for x in backups)}
