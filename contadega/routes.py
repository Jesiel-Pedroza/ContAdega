import base64, csv, io
from pathlib import Path
from datetime import timedelta
from uuid import UUID
from functools import wraps
import qrcode
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .models import AuditLog, Cellar, ExpectedStock, Inventory, InventoryScope, OfflineOperation, OfflinePackage, Position, Role, Sector, StockHistory, User, Wine, now
from .operations import REPORT_TYPES, audit, create_backup, csv_bytes, filtered_report, maintenance_info
from .services import (CSV_FIELDS, ROLES, acquire_position, adjust_stock, approve_inventory,
 classify_inventory, create_cellar, create_first_admin, create_inventory, create_position,
 create_sector, create_user, create_wine, finish_position, import_wines, parse_csv,
 save_count, start_inventory, transition_inventory, apply_offline_operation, OFFLINE_STAGE_STATUS)

bp=Blueprint("main",__name__)
attempts={}
def current_user(): return db.session.get(User, session.get("user_id")) if session.get("user_id") else None
def login_required(view):
    @wraps(view)
    def wrapped(*a,**kw):
        if not current_user(): flash("Faça login para continuar.","erro"); return redirect(url_for("main.login",next=request.path))
        return view(*a,**kw)
    return wrapped
def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*a,**kw):
            if not current_user().has_role(role): abort(403)
            return view(*a,**kw)
        return wrapped
    return decorator
@bp.app_context_processor
def helpers(): return {"current_user":current_user(),"roles":ROLES}
@bp.route("/")
def index(): return redirect(url_for("main.setup" if not User.query.first() else "main.dashboard"))
@bp.get("/offline")
def offline():
    response=render_template("offline.html"); return response,200,{"Cache-Control":"public, max-age=86400"}
@bp.get("/service-worker.js")
def service_worker():
    response=send_from_directory(current_app.static_folder,"service-worker.js",mimetype="application/javascript",max_age=0)
    response.headers["Service-Worker-Allowed"]="/"; response.headers["Cache-Control"]="no-cache"; return response
@bp.route("/primeiro-acesso",methods=["GET","POST"])
def setup():
    if User.query.first(): abort(404)
    if request.method=="POST":
        try: create_first_admin(request.form.get("name"),request.form.get("username"),request.form.get("password",""),request.form.get("confirmation","")); flash("Administrador criado. Entre no sistema.","sucesso"); return redirect(url_for("main.login"))
        except ValueError as e: flash(str(e),"erro")
    return render_template("setup.html")
@bp.route("/login",methods=["GET","POST"])
def login():
    if not User.query.first(): return redirect(url_for("main.setup"))
    if request.method=="POST":
        key=request.remote_addr or "local"; state=attempts.get(key,{"count":0,"until":0})
        import time
        if state["until"]>time.time(): flash("Muitas tentativas. Aguarde um minuto.","erro"); return render_template("login.html"),429
        user=User.query.filter(User.username==request.form.get("username","").strip()).first()
        if not user or not user.active or not user.check_password(request.form.get("password","")):
            state["count"]+=1
            if state["count"]>=5: state={"count":0,"until":time.time()+60}
            attempts[key]=state; flash("Usuário ou senha inválidos.","erro")
        else: attempts.pop(key,None); session.clear(); session["user_id"]=user.id; user.last_login=now(); audit("login",user); db.session.commit(); return redirect(url_for("main.dashboard"))
    return render_template("login.html")
@bp.post("/logout")
@login_required
def logout():
    user_id=session.get("user_id"); session.clear(); flash("Sessão encerrada.","sucesso")
    response=redirect(url_for("main.login")); response.set_cookie("contadega_logout",str(user_id),max_age=60,samesite="Lax")
    return response

def can_count(user, stage):
    role={"primeira":"contador","segunda":"conferente","recontagem":"conferente"}.get(stage)
    return bool(role and (user.has_role(role) or user.has_role("administrador")))

@bp.get("/api/offline/inventarios/<int:inventory_id>/pacote")
@login_required
def offline_package(inventory_id):
    inv=db.get_or_404(Inventory,inventory_id); stage=request.args.get("stage","primeira"); user=current_user()
    if not can_count(user,stage) or inv.status!=OFFLINE_STAGE_STATUS.get(stage): abort(403)
    expires=now()+timedelta(hours=8)
    package=OfflinePackage.query.filter_by(user_id=user.id,inventory_id=inv.id,stage=stage).first()
    if not package: package=OfflinePackage(user_id=user.id,inventory_id=inv.id,stage=stage,expires_at=expires); db.session.add(package)
    else: package.issued_at=now(); package.expires_at=expires; package.revoked_at=None
    db.session.commit()
    scopes=[{"id":s.id,"version":s.version,"position":{"id":s.position.id,"code":s.position.code,"qr_code":s.position.qr_code},"finished":bool(getattr(s,{"primeira":"first_finished_at","segunda":"second_finished_at","recontagem":"recount_finished_at"}[stage]))} for s in inv.scopes]
    wines=[{"id":w.id,"name":w.name,"producer":w.producer,"vintage":w.vintage,"barcode":w.barcode} for w in Wine.query.filter_by(active=True).order_by(Wine.name)]
    response=jsonify(package_id=package.id,user_id=user.id,inventory={"id":inv.id,"name":inv.name,"status":inv.status},stage=stage,issued_at=package.issued_at.isoformat()+"Z",expires_at=package.expires_at.isoformat()+"Z",server_time=now().isoformat()+"Z",scopes=scopes,wines=wines)
    response.headers["Cache-Control"]="no-store, private"; return response

@bp.post("/api/offline/sincronizar")
@login_required
def offline_sync():
    if request.content_length and request.content_length>262144: return jsonify(error="payload_too_large",server_time=now().isoformat()+"Z"),413
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or not isinstance(body.get("operations"),list) or len(body["operations"])>100: return jsonify(error="invalid_payload",server_time=now().isoformat()+"Z"),400
    package=db.session.get(OfflinePackage,body.get("package_id")); user=current_user()
    if not package or package.user_id!=user.id: abort(403)
    results=[]
    for data in body["operations"]:
        try:
            required={"id":str,"scope_id":int,"wine_id":int,"sequence":int,"base_version":int,"quantity":int,"device_id":str}
            if not isinstance(data,dict) or any(not isinstance(data.get(k),t) for k,t in required.items()) or data["quantity"]<0 or data["sequence"]<1 or len(data["device_id"])>64: raise ValueError
            UUID(data["id"])
        except (ValueError,TypeError): db.session.rollback(); return jsonify(error="invalid_payload",server_time=now().isoformat()+"Z"),400
        existing=db.session.get(OfflineOperation,data["id"])
        if existing:
            results.append({"id":existing.id,"status":existing.status,"error":existing.error_code,"idempotent":True}); continue
        try:
            op=apply_offline_operation(package,data,user); db.session.flush(); results.append({"id":op.id,"status":op.status,"error":op.error_code,"idempotent":False})
        except IntegrityError:
            db.session.rollback(); return jsonify(error="sequence_conflict",server_time=now().isoformat()+"Z"),409
    if any(x["status"]!="applied" for x in results): audit("conflito_offline",user,package,{"resultados":results})
    db.session.commit()
    response=jsonify(results=results,server_time=now().isoformat()+"Z"); response.headers["Cache-Control"]="no-store, private"; return response
@bp.get("/painel")
@login_required
def dashboard():
    active=Inventory.query.filter(Inventory.status.notin_(["rascunho","cancelado","aprovado"])).order_by(Inventory.id.desc()).first()
    total=len(active.scopes) if active else 0; done=sum(bool(s.first_finished_at) for s in active.scopes) if active else 0
    last=Inventory.query.filter_by(status="aprovado").order_by(Inventory.approved_at.desc()).first()
    counts={"Vinhos cadastrados":Wine.query.count(),"Garrafas esperadas":db.session.query(db.func.coalesce(db.func.sum(ExpectedStock.quantity),0)).scalar(),"Inventários em andamento":Inventory.query.filter(Inventory.status.notin_(["rascunho","cancelado","aprovado"])).count(),"Inventário atual":f"{round(done*100/total) if total else 0}%","Posições pendentes":max(total-done,0),"Divergências":sum(r["classification"]!="correto" for r in classify_inventory(active)) if active else 0,"Sincronizações com conflito":OfflineOperation.query.filter_by(status="rejected").count(),"Último inventário aprovado":last.approved_at.strftime("%d/%m/%Y") if last and last.approved_at else "—"}
    return render_template("dashboard.html",counts=counts,active=active)

RESOURCES={"usuarios":(User,create_user),"vinhos":(Wine,create_wine),"adegas":(Cellar,create_cellar),"setores":(Sector,create_sector),"posicoes":(Position,create_position)}
@bp.route("/<resource>",methods=["GET","POST"])
@role_required("administrador")
def resource(resource):
    if resource not in RESOURCES: abort(404)
    model,creator=RESOURCES[resource]
    if request.method=="POST":
        try:
            obj=creator(request.form); audit("cadastro_criado",current_user(),obj,{"recurso":resource}); db.session.commit(); flash("Cadastro salvo com sucesso.","sucesso"); return redirect(url_for("main.resource",resource=resource))
        except (ValueError,IntegrityError,KeyError) as e: db.session.rollback(); flash(str(e) if isinstance(e,ValueError) else "Não foi possível salvar: dado duplicado ou inválido.","erro")
    return render_template("resource.html",resource=resource,items=model.query.order_by(model.id.desc()).all(),cellars=Cellar.query.all(),sectors=Sector.query.all())
@bp.post("/<resource>/<int:item_id>/excluir")
@role_required("administrador")
def delete_resource(resource,item_id):
    if resource not in RESOURCES: abort(404)
    if resource=="usuarios" and item_id==current_user().id: flash("Você não pode excluir seu próprio usuário.","erro")
    else:
        obj=db.get_or_404(RESOURCES[resource][0],item_id); db.session.delete(obj)
        try: db.session.commit(); flash("Cadastro excluído.","sucesso")
        except IntegrityError: db.session.rollback(); flash("Cadastro em uso; desative-o em vez de excluir.","erro")
    return redirect(url_for("main.resource",resource=resource))
@bp.get("/posicoes/<int:item_id>/qr")
@role_required("administrador")
def position_qr(item_id):
    item=db.get_or_404(Position,item_id); image=qrcode.make(item.qr_code); output=io.BytesIO(); image.save(output,format="PNG"); encoded=base64.b64encode(output.getvalue()).decode(); return render_template("qr.html",item=item,qr=encoded)

@bp.route("/posicoes/etiquetas",methods=["GET","POST"])
@role_required("administrador")
def position_labels():
    ids=request.values.getlist("positions"); selected=Position.query.filter(Position.id.in_(ids)).order_by(Position.code).all() if ids else []
    labels=[]
    for item in selected:
        image=qrcode.make(item.qr_code); output=io.BytesIO(); image.save(output,format="PNG")
        labels.append((item,base64.b64encode(output.getvalue()).decode()))
    return render_template("labels.html",positions=Position.query.filter_by(active=True).order_by(Position.code).all(),labels=labels,size=request.values.get("size","medium"))
@bp.get("/vinhos/modelo.csv")
@role_required("administrador")
def csv_template(): return send_file(io.BytesIO((";".join(CSV_FIELDS)+"\nVinho Exemplo;Produtor;Brasil;Serra Gaúcha;Tinto;Merlot;2020;750;7890000000000;\n").encode()),mimetype="text/csv",as_attachment=True,download_name="modelo-vinhos.csv")
@bp.route("/vinhos/importar",methods=["GET","POST"])
@role_required("administrador")
def csv_import():
    preview=session.get("csv_preview",[])
    if request.method=="POST":
        if request.form.get("confirm")=="yes":
            if not preview: flash("Nenhuma importação válida para confirmar.","erro")
            else: import_wines(preview); session.pop("csv_preview",None); flash(f"{len(preview)} vinhos importados.","sucesso"); return redirect(url_for("main.resource",resource="vinhos"))
        else:
            file=request.files.get("file")
            if not file: flash("Selecione um arquivo CSV.","erro")
            else:
                preview,errors=parse_csv(file.read()); session["csv_preview"]=preview if not errors else []
                for error in errors: flash(error,"erro")
                if preview and not errors: flash("Arquivo válido. Revise e confirme.","sucesso")
    return render_template("import.html",preview=preview)

@bp.route("/estoque",methods=["GET","POST"])
@role_required("administrador")
def stock():
    if request.method=="POST":
        try:
            position=db.get_or_404(Position,int(request.form["position_id"])); adjust_stock(position,db.get_or_404(Wine,int(request.form["wine_id"])),request.form["quantity"],current_user(),request.form.get("reason")); audit("estoque_ajustado",current_user(),position); db.session.commit(); flash("Estoque ajustado e histórico registrado.","sucesso"); return redirect(url_for("main.stock"))
        except ValueError as e: db.session.rollback(); flash(str(e),"erro")
    q=request.args.get("q","").strip(); query=ExpectedStock.query.join(Position).join(Wine)
    if q: query=query.filter(or_(Position.code.ilike(f"%{q}%"),Wine.name.ilike(f"%{q}%"),Wine.producer.ilike(f"%{q}%")))
    return render_template("stock.html",stocks=query.order_by(Position.code,Wine.name).all(),positions=Position.query.filter_by(active=True).all(),wines=Wine.query.filter_by(active=True).all(),history=StockHistory.query.order_by(StockHistory.id.desc()).limit(30).all())

@bp.get("/estoque/exportar.csv")
@role_required("administrador")
def stock_export():
    out=io.StringIO(); writer=csv.writer(out,delimiter=";"); writer.writerow(["adega","posicao","vinho_id","vinho","quantidade"])
    for x in ExpectedStock.query.join(Position).join(Wine).order_by(Position.code).all(): writer.writerow([x.position.sector.cellar.name,x.position.code,x.wine_id,x.wine.name,x.quantity])
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),mimetype="text/csv",as_attachment=True,download_name="estoque-atual.csv")

@bp.post("/estoque/importar")
@role_required("administrador")
def stock_import():
    try:
        rows=csv.DictReader(io.StringIO(request.files["file"].read().decode("utf-8-sig")),delimiter=";")
        for row in rows: adjust_stock(db.session.get(Position,int(row["posicao_id"])),db.session.get(Wine,int(row["vinho_id"])),row["quantidade"],current_user(),"Importação CSV",commit=False)
        audit("estoque_importado",current_user(),detail={"linhas":rows.line_num-1}); db.session.commit(); flash("Estoque importado.","sucesso")
    except Exception: db.session.rollback(); flash("CSV inválido; nenhuma linha foi aplicada.","erro")
    return redirect(url_for("main.stock"))

@bp.get("/relatorios")
@role_required("administrador")
def reports():
    kind=request.args.get("tipo","geral"); kind=kind if kind in REPORT_TYPES else "geral"; rows=filtered_report(kind,request.args)
    if request.args.get("formato")=="csv":
        audit("relatorio_exportado",current_user(),detail={"tipo":kind,"linhas":len(rows)}); db.session.commit()
        return send_file(io.BytesIO(csv_bytes(rows,request.args.get("separador",";") if request.args.get("separador") in {";",","} else ";")),mimetype="text/csv",as_attachment=True,download_name=f"relatorio-{kind}.csv")
    return render_template("reports.html",types=REPORT_TYPES,kind=kind,rows=rows,inventories=Inventory.query.order_by(Inventory.id.desc()).all())

@bp.route("/administracao/manutencao",methods=["GET","POST"])
@role_required("administrador")
def maintenance():
    if request.method=="POST":
        try:
            target=create_backup(); audit("backup_criado",current_user(),detail={"arquivo":target.name}); db.session.commit(); flash(f"Backup verificado criado em {target}.","sucesso")
        except (ValueError,RuntimeError) as exc: flash(str(exc),"erro")
    return render_template("maintenance.html",info=maintenance_info())

@bp.route("/inventarios",methods=["GET","POST"])
@login_required
def inventories():
    if request.method=="POST":
        if not current_user().has_role("administrador"): abort(403)
        try:
            cellar=db.get_or_404(Cellar,int(request.form["cellar_id"])); positions=Position.query.filter(Position.id.in_(request.form.getlist("positions")),Position.cellar_id==cellar.id).all(); inv=create_inventory(request.form.get("name"),cellar,positions,current_user(),request.form.get("notes")); audit("inventario_criado",current_user(),inv); db.session.commit(); flash("Inventário criado.","sucesso"); return redirect(url_for("main.inventories"))
        except ValueError as e: flash(str(e),"erro")
    return render_template("inventories.html",inventories=Inventory.query.order_by(Inventory.id.desc()).all(),cellars=Cellar.query.filter_by(active=True).all(),positions=Position.query.filter_by(active=True).all())

@bp.post("/inventarios/<int:inventory_id>/iniciar")
@role_required("administrador")
def inventory_start(inventory_id):
    try:
        inv=db.get_or_404(Inventory,inventory_id); start_inventory(inv); audit("inventario_aberto",current_user(),inv); db.session.commit(); flash("Inventário iniciado; snapshot criado.","sucesso")
    except ValueError as e: flash(str(e),"erro")
    return redirect(url_for("main.inventory_detail",inventory_id=inventory_id))

@bp.route("/inventarios/<int:inventory_id>",methods=["GET","POST"])
@login_required
def inventory_detail(inventory_id):
    inv=db.get_or_404(Inventory,inventory_id)
    if request.method=="POST":
        if not current_user().has_role("administrador"): abort(403)
        action=request.form.get("action")
        try:
            if action=="transition":
                transition_inventory(inv,request.form["status"]); audit("inventario_cancelado" if request.form["status"]=="cancelado" else "inventario_etapa_alterada",current_user(),inv,{"status":request.form["status"]}); db.session.commit()
            elif action=="approve": approve_inventory(inv,current_user(),request.form.get("apply_stock")=="yes",request.form.get("justification")); audit("inventario_aprovado",current_user(),inv,{"estoque_aplicado":request.form.get("apply_stock")=="yes"}); db.session.commit()
            else: abort(400)
            flash("Operação concluída.","sucesso")
        except (ValueError,PermissionError) as e: db.session.rollback(); flash(str(e),"erro")
        return redirect(url_for("main.inventory_detail",inventory_id=inv.id))
    report=classify_inventory(inv); done=sum(bool(s.first_finished_at) for s in inv.scopes); total=len(inv.scopes)
    return render_template("inventory.html",inventory=inv,report=report,done=done,total=total,percent=round(done*100/total) if total else 0)

@bp.route("/inventarios/<int:inventory_id>/posicoes/<int:scope_id>/<stage>",methods=["GET","POST"])
@login_required
def inventory_count(inventory_id,scope_id,stage):
    inv=db.get_or_404(Inventory,inventory_id); scope=db.get_or_404(InventoryScope,scope_id)
    if scope.inventory_id!=inv.id or stage not in {"primeira","segunda","recontagem"}: abort(404)
    required={"primeira":"contador","segunda":"conferente","recontagem":"conferente"}[stage]
    if not (current_user().has_role(required) or current_user().has_role("administrador")): abort(403)
    token=session.setdefault("device_token",__import__("uuid").uuid4().hex)
    try: acquire_position(scope,current_user(),token)
    except ValueError as e: flash(str(e),"erro"); return redirect(url_for("main.inventory_detail",inventory_id=inv.id))
    if request.method=="POST":
        try:
            if request.form.get("finish"): finish_position(inv,scope,current_user(),stage,request.form.get("observation")); audit("posicao_finalizada" if stage!="recontagem" else "recontagem_finalizada",current_user(),scope,{"etapa":stage}); db.session.commit()
            else: save_count(inv,scope,db.get_or_404(Wine,int(request.form["wine_id"])),request.form["quantity"],current_user(),stage,request.form["version"],request.headers.get("User-Agent"),request.form.get("observation"))
            flash("Contagem registrada.","sucesso"); return redirect(url_for("main.inventory_count",inventory_id=inv.id,scope_id=scope.id,stage=stage))
        except ValueError as e: db.session.rollback(); flash(str(e),"erro")
    visible=[c for c in inv.counts if c.position_id==scope.position_id and c.stage==stage]
    if stage=="recontagem":
        divergent={(r["position_id"],r["wine_id"]) for r in classify_inventory(inv) if r["classification"]=="divergencia de conferência"}; wines=Wine.query.filter(Wine.id.in_([w for p,w in divergent if p==scope.position_id])).all()
    else: wines=Wine.query.filter_by(active=True).order_by(Wine.name).all()
    return render_template("count.html",inventory=inv,scope=scope,stage=stage,wines=wines,counts=visible)
