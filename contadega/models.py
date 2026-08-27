from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import UniqueConstraint, Index
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
