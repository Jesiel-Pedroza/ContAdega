from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db

user_roles = db.Table("user_roles", db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), db.Column("role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True))

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)

class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

class User(db.Model):
    __tablename__ = "users"
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(120), nullable=False); username=db.Column(db.String(80, collation="NOCASE"), nullable=False, unique=True); password_hash=db.Column(db.String(255), nullable=False); active=db.Column(db.Boolean, nullable=False, default=True); created_at=db.Column(db.DateTime, nullable=False, default=now); last_login=db.Column(db.DateTime)
    roles=db.relationship(Role, secondary=user_roles, lazy="selectin")
    def set_password(self, password): self.password_hash=generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def has_role(self, role): return any(r.name == role for r in self.roles)

class Wine(db.Model):
    __tablename__="wines"
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(150), nullable=False); producer=db.Column(db.String(150), nullable=False); country=db.Column(db.String(80), nullable=False); region=db.Column(db.String(100)); type=db.Column(db.String(60), nullable=False); grape=db.Column(db.String(100)); vintage=db.Column(db.Integer); volume_ml=db.Column(db.Integer, nullable=False); barcode=db.Column(db.String(64), unique=True); notes=db.Column(db.Text); active=db.Column(db.Boolean, nullable=False, default=True); created_at=db.Column(db.DateTime, nullable=False, default=now); updated_at=db.Column(db.DateTime, nullable=False, default=now, onupdate=now)

class Cellar(db.Model):
    __tablename__="cellars"
    id=db.Column(db.Integer, primary_key=True); name=db.Column(db.String(120), nullable=False, unique=True); description=db.Column(db.Text); active=db.Column(db.Boolean, nullable=False, default=True)
    sectors=db.relationship("Sector", back_populates="cellar", cascade="all, delete-orphan")

class Sector(db.Model):
    __tablename__="sectors"; __table_args__=(UniqueConstraint("cellar_id","code",name="uq_sector_cellar_code"),)
    id=db.Column(db.Integer, primary_key=True); cellar_id=db.Column(db.Integer, db.ForeignKey("cellars.id", ondelete="CASCADE"), nullable=False); code=db.Column(db.String(20), nullable=False); name=db.Column(db.String(100), nullable=False); display_order=db.Column(db.Integer, nullable=False, default=0); active=db.Column(db.Boolean, nullable=False, default=True)
    cellar=db.relationship(Cellar, back_populates="sectors"); positions=db.relationship("Position", back_populates="sector", cascade="all, delete-orphan")

class Position(db.Model):
    __tablename__="positions"
    id=db.Column(db.Integer, primary_key=True); sector_id=db.Column(db.Integer, db.ForeignKey("sectors.id", ondelete="CASCADE"), nullable=False); cellar_id=db.Column(db.Integer, db.ForeignKey("cellars.id", ondelete="CASCADE"), nullable=False); code=db.Column(db.String(30, collation="NOCASE"), nullable=False); description=db.Column(db.Text); display_order=db.Column(db.Integer, nullable=False, default=0); capacity=db.Column(db.Integer); active=db.Column(db.Boolean, nullable=False, default=True); qr_code=db.Column(db.String(36), unique=True, nullable=False, default=lambda:str(uuid4()))
    sector=db.relationship(Sector, back_populates="positions")
    __table_args__=(UniqueConstraint("cellar_id","code",name="uq_position_cellar_code"),)

class ExpectedStock(db.Model):
    __tablename__="expected_stocks"; __table_args__=(UniqueConstraint("position_id","wine_id",name="uq_stock_position_wine"),CheckConstraint("quantity >= 0",name="ck_stock_nonnegative"))
    id=db.Column(db.Integer,primary_key=True); cellar_id=db.Column(db.Integer,db.ForeignKey("cellars.id"),nullable=False); position_id=db.Column(db.Integer,db.ForeignKey("positions.id"),nullable=False); wine_id=db.Column(db.Integer,db.ForeignKey("wines.id"),nullable=False); quantity=db.Column(db.Integer,nullable=False,default=0); updated_at=db.Column(db.DateTime,nullable=False,default=now,onupdate=now); updated_by_id=db.Column(db.Integer,db.ForeignKey("users.id"),nullable=False)
    position=db.relationship(Position); wine=db.relationship(Wine); updated_by=db.relationship(User)

class StockHistory(db.Model):
    __tablename__="stock_history"; __table_args__=(CheckConstraint("quantity_before >= 0 AND quantity_after >= 0",name="ck_history_nonnegative"),)
    id=db.Column(db.Integer,primary_key=True); stock_id=db.Column(db.Integer,db.ForeignKey("expected_stocks.id")); cellar_id=db.Column(db.Integer,db.ForeignKey("cellars.id"),nullable=False); position_id=db.Column(db.Integer,db.ForeignKey("positions.id"),nullable=False); wine_id=db.Column(db.Integer,db.ForeignKey("wines.id"),nullable=False); quantity_before=db.Column(db.Integer,nullable=False); quantity_after=db.Column(db.Integer,nullable=False); kind=db.Column(db.String(20),nullable=False); reason=db.Column(db.Text,nullable=False); user_id=db.Column(db.Integer,db.ForeignKey("users.id"),nullable=False); created_at=db.Column(db.DateTime,nullable=False,default=now)

class Inventory(db.Model):
    __tablename__="inventories"
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(150),nullable=False); cellar_id=db.Column(db.Integer,db.ForeignKey("cellars.id"),nullable=False); status=db.Column(db.String(30),nullable=False,default="rascunho"); created_by_id=db.Column(db.Integer,db.ForeignKey("users.id"),nullable=False); created_at=db.Column(db.DateTime,nullable=False,default=now); started_at=db.Column(db.DateTime); completed_at=db.Column(db.DateTime); approved_at=db.Column(db.DateTime); approved_by_id=db.Column(db.Integer,db.ForeignKey("users.id")); notes=db.Column(db.Text)
    cellar=db.relationship(Cellar); scopes=db.relationship("InventoryScope",cascade="all, delete-orphan",back_populates="inventory"); counts=db.relationship("InventoryCount",cascade="all, delete-orphan")

class InventoryScope(db.Model):
    __tablename__="inventory_scopes"; __table_args__=(UniqueConstraint("inventory_id","position_id",name="uq_inventory_position"),)
    id=db.Column(db.Integer,primary_key=True); inventory_id=db.Column(db.Integer,db.ForeignKey("inventories.id",ondelete="CASCADE"),nullable=False); position_id=db.Column(db.Integer,db.ForeignKey("positions.id"),nullable=False); first_finished_at=db.Column(db.DateTime); second_finished_at=db.Column(db.DateTime); recount_finished_at=db.Column(db.DateTime); first_user_id=db.Column(db.Integer,db.ForeignKey("users.id")); lock_token=db.Column(db.String(64)); lock_user_id=db.Column(db.Integer,db.ForeignKey("users.id")); version=db.Column(db.Integer,nullable=False,default=1)
    inventory=db.relationship(Inventory,back_populates="scopes"); position=db.relationship(Position); snapshots=db.relationship("InventorySnapshot",cascade="all, delete-orphan")

class InventorySnapshot(db.Model):
    __tablename__="inventory_snapshots"; __table_args__=(UniqueConstraint("scope_id","wine_id",name="uq_snapshot_wine"),CheckConstraint("quantity >= 0",name="ck_snapshot_nonnegative"))
    id=db.Column(db.Integer,primary_key=True); scope_id=db.Column(db.Integer,db.ForeignKey("inventory_scopes.id",ondelete="CASCADE"),nullable=False); wine_id=db.Column(db.Integer,db.ForeignKey("wines.id"),nullable=False); quantity=db.Column(db.Integer,nullable=False); wine=db.relationship(Wine)

class InventoryCount(db.Model):
    __tablename__="inventory_counts"; __table_args__=(UniqueConstraint("inventory_id","position_id","wine_id","stage",name="uq_count_stage"),CheckConstraint("quantity >= 0",name="ck_count_nonnegative"))
    id=db.Column(db.Integer,primary_key=True); inventory_id=db.Column(db.Integer,db.ForeignKey("inventories.id",ondelete="CASCADE"),nullable=False); position_id=db.Column(db.Integer,db.ForeignKey("positions.id"),nullable=False); wine_id=db.Column(db.Integer,db.ForeignKey("wines.id"),nullable=False); stage=db.Column(db.String(20),nullable=False); quantity=db.Column(db.Integer,nullable=False); user_id=db.Column(db.Integer,db.ForeignKey("users.id"),nullable=False); device=db.Column(db.String(120)); counted_at=db.Column(db.DateTime,nullable=False,default=now); observation=db.Column(db.Text); version=db.Column(db.Integer,nullable=False,default=1)
    wine=db.relationship(Wine); position=db.relationship(Position); user=db.relationship(User)
