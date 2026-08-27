from datetime import timedelta
from uuid import uuid4
import pytest
from contadega.extensions import db
from contadega.models import (Cellar, InventoryCount, OfflineAudit, OfflineOperation,
 OfflinePackage, Position, Sector, User, Wine, now)
from contadega.services import create_inventory, finish_position, start_inventory


def scenario(app):
    with app.app_context():
        admin=User(name="Admin",username="offline",roles=list(__import__('contadega.models',fromlist=['Role']).Role.query.all())); admin.set_password("12345678")
        cellar=Cellar(name="Offline"); sector=Sector(cellar=cellar,code="O",name="Offline"); db.session.add_all([admin,sector]); db.session.flush()
        position=Position(cellar_id=cellar.id,sector=sector,code="O1"); wine=Wine(name="Offline Wine",producer="P",country="BR",type="Tinto",volume_ml=750,barcode="7891234567890"); db.session.add_all([position,wine]); db.session.commit()
        inv=create_inventory("Offline",cellar,[position],admin); start_inventory(inv)
        return admin.id,inv.id,inv.scopes[0].id,wine.id

def login(client,user_id):
    with client.session_transaction() as session: session["user_id"]=user_id

def package(client,inventory_id):
    response=client.get(f"/api/offline/inventarios/{inventory_id}/pacote?stage=primeira")
    return response,response.get_json()

def operation(scope_id,wine_id,version=1,device="device-a",sequence=1):
    return {"id":str(uuid4()),"scope_id":scope_id,"wine_id":wine_id,"sequence":sequence,"base_version":version,"quantity":3,"device_id":device}

def sync(client,package_id,operations): return client.post("/api/offline/sincronizar",json={"package_id":package_id,"operations":operations})

def test_authorized_package_is_private_and_unauthorized(client,app):
    user,inventory,_,_=scenario(app); login(client,user); response,data=package(client,inventory)
    assert response.status_code==200 and response.headers["Cache-Control"]=="no-store, private" and data["user_id"]==user and data["expires_at"]>data["issued_at"]
    with client.session_transaction() as session: session.clear()
    assert client.get(f"/api/offline/inventarios/{inventory}/pacote").status_code==302

def test_expired_package_rejects_and_audits(client,app):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory)
    with app.app_context(): pkg=db.session.get(OfflinePackage,data["package_id"]); pkg.expires_at=now()-timedelta(seconds=1); db.session.commit()
    response=sync(client,data["package_id"],[operation(scope,wine)])
    assert response.get_json()["results"][0]["error"]=="package_expired"
    with app.app_context(): assert OfflineOperation.query.one().status=="rejected" and OfflineAudit.query.one().event=="rejected"

def test_idempotent_resend_applies_once(client,app):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory); op=operation(scope,wine)
    first=sync(client,data["package_id"],[op]).get_json(); second=sync(client,data["package_id"],[op]).get_json()
    assert first["results"][0]["status"]=="applied" and second["results"][0]["idempotent"] is True
    with app.app_context(): assert InventoryCount.query.count()==1 and OfflineOperation.query.count()==1

def test_invalid_payload_rolls_back(client,app):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory)
    valid=operation(scope,wine); invalid=operation(scope,wine,version=2,sequence=2); invalid["quantity"]=-1
    response=sync(client,data["package_id"],[valid,invalid])
    assert response.status_code==400 and response.get_json()["error"]=="invalid_payload"
    with app.app_context(): assert InventoryCount.query.count()==0 and OfflineOperation.query.count()==0

def test_version_conflict_and_two_devices_are_preserved(client,app):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory)
    first=operation(scope,wine,device="phone-a"); second=operation(scope,wine,device="phone-b")
    result=sync(client,data["package_id"],[first,second]).get_json()["results"]
    assert [x["status"] for x in result]==["applied","rejected"] and result[1]["error"]=="version_conflict"
    with app.app_context(): assert OfflineOperation.query.count()==2 and OfflineAudit.query.count()==2

@pytest.mark.parametrize("state,error",(("finished","position_finished"),("cancelado","inventory_cancelado"),("aprovado","inventory_aprovado")))
def test_finished_position_cancelled_and_approved(client,app,state,error):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory)
    with app.app_context():
        pkg=db.session.get(OfflinePackage,data["package_id"]); inv=pkg.inventory
        if state=="finished": finish_position(inv,inv.scopes[0],db.session.get(User,user),"primeira")
        else: inv.status=state; db.session.commit()
    result=sync(client,data["package_id"],[operation(scope,wine)]).get_json()["results"][0]
    assert result["error"]==error

def test_logout_marks_explicit_cleanup_without_server_queue_loss(client,app):
    user,inventory,scope,wine=scenario(app); login(client,user); _,data=package(client,inventory); sync(client,data["package_id"],[operation(scope,wine)])
    response=client.post("/logout")
    assert response.status_code==302 and f"contadega_logout={user}" in response.headers["Set-Cookie"]
    with app.app_context(): assert OfflineOperation.query.count()==1

def test_manifest_worker_fallback_queue_resume_and_manual_entry(client):
    manifest=client.get("/static/manifest.webmanifest").get_json()
    assert manifest["display"]=="standalone" and manifest["icons"]==[{"src":"/static/icons/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]
    worker=client.get("/service-worker.js"); text=worker.get_data(as_text=True)
    assert worker.status_code==200 and worker.headers["Service-Worker-Allowed"]=="/" and "contadega-static-v3" in text and "caches.match('/offline')" in text and "startsWith('/api/')" in text
    assert client.get("/offline").status_code==200
    js=client.get("/static/offline.js").get_data(as_text=True)
    assert "indexedDB.open" in js and "localStorage" not in js and "status==='pending'" in js and "input" not in ""
    template=open("contadega/templates/count.html",encoding="utf-8").read()
    assert 'id="quantity"' in template and 'id="scan-product"' in template and "entrada manual acima" in template
