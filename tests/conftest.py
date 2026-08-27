import pytest
from contadega import create_app
from contadega.extensions import db
from contadega.models import Role
@pytest.fixture
def app(tmp_path):
 app=create_app({"TESTING":True,"SECRET_KEY":"test","SQLALCHEMY_DATABASE_URI":f"sqlite:///{tmp_path/'test.sqlite'}","WTF_CSRF_ENABLED":False})
 with app.app_context():
  db.create_all(); db.session.add_all(Role(name=x) for x in ("administrador","contador","conferente")); db.session.commit()
 yield app
@pytest.fixture
def client(app): return app.test_client()
@pytest.fixture
def admin(client):
 client.post("/primeiro-acesso",data={"name":"Admin","username":"admin","password":"segura123","confirmation":"segura123"}); client.post("/login",data={"username":"admin","password":"segura123"}); return client
