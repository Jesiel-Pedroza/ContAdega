import io
import pytest
from sqlalchemy.exc import IntegrityError
from contadega import create_app
from contadega.extensions import db
from contadega.models import Cellar, Position, Role, Sector, User, Wine
def test_first_admin_and_second_setup_blocked(client,app):
 response=client.post("/primeiro-acesso",data={"name":"Ana","username":"ADMIN","password":"segura123","confirmation":"segura123"}); assert response.status_code==302
 with app.app_context(): assert User.query.one().has_role("administrador")
 assert client.get("/primeiro-acesso").status_code==404
def test_login_correct_and_incorrect(client):
 client.post("/primeiro-acesso",data={"name":"Ana","username":"admin","password":"segura123","confirmation":"segura123"}); assert b"inv\xc3\xa1lidos" in client.post("/login",data={"username":"admin","password":"errada"}).data; assert client.post("/login",data={"username":"ADMIN","password":"segura123"}).status_code==302
def test_private_and_authorization(client,app):
 assert client.get("/painel").status_code==302
 with app.app_context():
  role=Role.query.filter_by(name="contador").one(); u=User(name="C",username="c",roles=[role]); u.set_password("segura123"); db.session.add(u); db.session.commit()
 client.post("/login",data={"username":"c","password":"segura123"}); assert client.get("/vinhos").status_code==403
def test_crud_main_resources(admin,app):
 assert admin.post("/adegas",data={"name":"Principal","description":"Subsolo"}).status_code==302
 with app.app_context(): cellar_id=Cellar.query.one().id
 assert admin.post("/setores",data={"cellar_id":cellar_id,"code":"A","name":"A","display_order":1}).status_code==302
 with app.app_context(): sector_id=Sector.query.one().id
 assert admin.post("/posicoes",data={"sector_id":sector_id,"code":"A01","display_order":1}).status_code==302; assert admin.post("/vinhos",data={"name":"Reserva","producer":"P","country":"Brasil","type":"Tinto","volume_ml":750,"barcode":"123"}).status_code==302
 with app.app_context(): assert (Cellar.query.count(),Sector.query.count(),Position.query.count(),Wine.query.count())==(1,1,1,1)
def test_database_uniqueness(app):
 with app.app_context():
  r=Role.query.first(); a=User(name="A",username="Same",roles=[r]); a.set_password("segura123"); b=User(name="B",username="same",roles=[r]); b.set_password("segura123"); db.session.add_all([a,b]); pytest.raises(IntegrityError,db.session.commit); db.session.rollback()
  db.session.add_all([Wine(name="A",producer="P",country="B",type="T",volume_ml=1,barcode="x"),Wine(name="B",producer="P",country="B",type="T",volume_ml=1,barcode="x")]); pytest.raises(IntegrityError,db.session.commit); db.session.rollback()
  c=Cellar(name="C"); db.session.add(c); db.session.flush(); s=Sector(cellar=c,code="A",name="A"); db.session.add(s); db.session.flush(); db.session.add_all([Position(sector=s,cellar_id=c.id,code="A01"),Position(sector=s,cellar_id=c.id,code="a01")]); pytest.raises(IntegrityError,db.session.commit); db.session.rollback()
def test_csv_valid_and_invalid_transaction(admin,app):
 header="nome;produtor;pais;regiao;tipo;uva;safra;volume_ml;codigo_barras;observacoes\n"; valid=(header+"V;P;Brasil;R;Tinto;U;2020;750;999;Ok\n").encode(); response=admin.post("/vinhos/importar",data={"file":(io.BytesIO(valid),"v.csv")},content_type="multipart/form-data"); assert b"Arquivo v\xc3\xa1lido" in response.data; admin.post("/vinhos/importar",data={"confirm":"yes"}); invalid=(header+"X;P;Brasil;;Tinto;;;abc;;\n").encode(); admin.post("/vinhos/importar",data={"file":(io.BytesIO(invalid),"i.csv")},content_type="multipart/form-data")
 with app.app_context(): assert Wine.query.count()==1
def test_csrf_and_foreign_keys(tmp_path):
 app=create_app({"TESTING":True,"SECRET_KEY":"x","SQLALCHEMY_DATABASE_URI":f"sqlite:///{tmp_path/'csrf.sqlite'}"})
 with app.app_context(): db.create_all(); assert db.session.execute(db.text("PRAGMA foreign_keys")).scalar()==1
 assert app.test_client().post("/primeiro-acesso",data={}).status_code==400
