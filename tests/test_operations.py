import sqlite3
from pathlib import Path
from contadega.extensions import db
from contadega.models import AuditLog, Cellar, Position, Sector
from contadega.operations import create_backup, csv_bytes

def test_reports_authorization_csv_and_sensitive_fields(app,client,admin):
    client.post("/logout")
    assert client.get("/relatorios").status_code in (302,303)
    client.post("/login",data={"username":"admin","password":"segura123"})
    response=client.get("/relatorios?tipo=vinhos&formato=csv")
    assert response.status_code==200
    assert response.data.startswith(b"\xef\xbb\xbf")
    assert b"password_hash" not in response.data and b"session" not in response.data
    with app.app_context(): assert AuditLog.query.filter_by(action="relatorio_exportado").count()==1

def test_labels_are_admin_only_and_contain_no_secret(app,client,admin):
    with app.app_context():
        cellar=Cellar(name="Principal"); sector=Sector(cellar=cellar,code="A",name="A"); db.session.add_all([cellar,sector]); db.session.flush(); position=Position(cellar_id=cellar.id,sector=sector,code="A01"); db.session.add(position); db.session.commit(); position_id=position.id; qr=position.qr_code
    response=client.post("/posicoes/etiquetas",data={"positions":str(position_id),"size":"small"})
    assert response.status_code==200
    assert qr.encode() not in response.data
    assert b"position-label" in response.data

def test_consistent_backup_and_integrity(app,tmp_path):
    with app.app_context():
        app.config["BACKUP_DIRECTORY"]=str(tmp_path); target=create_backup()
        assert target.is_file()
        with sqlite3.connect(target) as connection: assert connection.execute("PRAGMA integrity_check").fetchone()[0]=="ok"

def test_csv_excel_format():
    value=csv_bytes([{"vinho":"Ação","quantidade":2}])
    assert value.startswith(b"\xef\xbb\xbf") and b"vinho;quantidade\r\n" in value

def test_security_headers(client):
    response=client.get("/offline")
    assert response.headers["X-Content-Type-Options"]=="nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
