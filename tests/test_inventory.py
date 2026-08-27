import pytest
from contadega.extensions import db
from contadega.models import (Cellar, ExpectedStock, InventoryCount, Position, Role,
 Sector, StockHistory, User, Wine)
from contadega.services import (adjust_stock, approve_inventory, classify_inventory,
 create_inventory, finish_position, save_count, start_inventory, transition_inventory)

def fixtures(app):
 admin=User(name="Admin",username="a",roles=[Role.query.filter_by(name="administrador").one()]); admin.set_password("12345678")
 counter=User(name="Contador",username="c",roles=[Role.query.filter_by(name="contador").one()]); counter.set_password("12345678")
 checker=User(name="Conferente",username="f",roles=[Role.query.filter_by(name="conferente").one()]); checker.set_password("12345678")
 cellar=Cellar(name="Adega"); sector=Sector(cellar=cellar,code="A",name="Setor A")
 db.session.add(sector); db.session.flush()
 p1=Position(cellar_id=cellar.id,sector=sector,code="A01"); p2=Position(cellar_id=cellar.id,sector=sector,code="A02")
 w1=Wine(name="Cabernet",producer="P",country="BR",type="Tinto",volume_ml=750); w2=Wine(name="Merlot",producer="P",country="BR",type="Tinto",volume_ml=750)
 db.session.add_all([admin,counter,checker,p1,p2,w1,w2]); db.session.commit()
 return admin,counter,checker,cellar,p1,p2,w1,w2

def test_stock_history_and_validation(app):
 with app.app_context():
  a,_,_,_,p,_,w,_=fixtures(app); adjust_stock(p,w,4,a,"Carga")
  assert ExpectedStock.query.one().quantity==4 and StockHistory.query.one().kind=="administrativa"
  with pytest.raises(ValueError): adjust_stock(p,w,-1,a,"inválido")

def test_snapshot_is_immutable_and_same_wine_multiple_positions(app):
 with app.app_context():
  a,_,_,c,p1,p2,w,_=fixtures(app); adjust_stock(p1,w,4,a,"carga"); adjust_stock(p2,w,2,a,"carga")
  inv=create_inventory("I",c,[p1,p2],a); start_inventory(inv); adjust_stock(p1,w,9,a,"depois")
  assert [s.snapshots[0].quantity for s in inv.scopes]==[4,2]

def test_state_machine_and_closed_inventory(app):
 with app.app_context():
  a,_,_,c,p,_,w,_=fixtures(app); inv=create_inventory("I",c,[p],a)
  with pytest.raises(ValueError): transition_inventory(inv,"aprovado")
  start_inventory(inv); transition_inventory(inv,"aguardando_conferencia"); transition_inventory(inv,"em_conferencia"); transition_inventory(inv,"aguardando_aprovacao"); approve_inventory(inv,a,False,"Confirmo")
  with pytest.raises(ValueError): save_count(inv,inv.scopes[0],w,1,a,"primeira",1)

def test_counts_multiple_wines_resume_lock_version_and_duplicate(app):
 with app.app_context():
  a,counter,_,cellar,p,_,w1,w2=fixtures(app); inv=create_inventory("I",cellar,[p],a); start_inventory(inv); scope=inv.scopes[0]
  save_count(inv,scope,w1,2,counter,"primeira",1); save_count(inv,scope,w2,3,counter,"primeira",2)
  assert InventoryCount.query.count()==2
  with pytest.raises(ValueError): save_count(inv,scope,w1,4,counter,"primeira",1)
  finish_position(inv,scope,counter,"primeira")
  with pytest.raises(ValueError): save_count(inv,scope,w1,4,counter,"primeira",scope.version)

def test_blind_second_count_and_divergence_classification(app):
 with app.app_context():
  a,counter,checker,cellar,p,_,w,_=fixtures(app); adjust_stock(p,w,4,a,"carga"); inv=create_inventory("I",cellar,[p],a); start_inventory(inv); s=inv.scopes[0]
  save_count(inv,s,w,4,counter,"primeira",1); finish_position(inv,s,counter,"primeira"); transition_inventory(inv,"aguardando_conferencia"); transition_inventory(inv,"em_conferencia")
  save_count(inv,s,w,3,checker,"segunda",s.version); finish_position(inv,s,checker,"segunda")
  assert classify_inventory(inv)[0]["classification"]=="divergencia de conferência"

@pytest.mark.parametrize("expected,found,kind",[(4,3,"falta"),(3,4,"sobra"),(4,0,"não encontrado"),(0,2,"produto inesperado")])
def test_deterministic_classifications(app,expected,found,kind):
 with app.app_context():
  a,counter,_,cellar,p,_,w,_=fixtures(app)
  if expected: adjust_stock(p,w,expected,a,"carga")
  inv=create_inventory("I",cellar,[p],a); start_inventory(inv)
  if found: save_count(inv,inv.scopes[0],w,found,counter,"primeira",1)
  assert classify_inventory(inv)[0]["classification"]==kind

def test_wrong_location_and_atomic_approval(app):
 with app.app_context():
  a,counter,_,cellar,p1,p2,w,_=fixtures(app); adjust_stock(p2,w,4,a,"carga"); inv=create_inventory("I",cellar,[p1,p2],a); start_inventory(inv)
  save_count(inv,inv.scopes[0],w,1,counter,"primeira",1); save_count(inv,inv.scopes[1],w,3,counter,"primeira",1)
  assert {x["classification"] for x in classify_inventory(inv)}=={"local incorreto"}
  transition_inventory(inv,"aguardando_conferencia"); transition_inventory(inv,"em_conferencia"); transition_inventory(inv,"aguardando_aprovacao"); approve_inventory(inv,a,True,"Aplicar físico")
  assert ExpectedStock.query.filter_by(position_id=p1.id,wine_id=w.id).one().quantity==1
  assert StockHistory.query.filter_by(kind="inventario").count()==2

def test_authorization_service(app):
 with app.app_context():
  a,counter,_,cellar,p,_,_,_=fixtures(app); inv=create_inventory("I",cellar,[p],a); start_inventory(inv); transition_inventory(inv,"aguardando_conferencia"); transition_inventory(inv,"em_conferencia"); transition_inventory(inv,"aguardando_aprovacao")
  with pytest.raises(PermissionError): approve_inventory(inv,counter,False,"confirmo")
