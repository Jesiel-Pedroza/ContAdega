import click
from flask import current_app
from .extensions import db
from .models import Cellar, Position, Role, Sector, User, Wine
from .services import adjust_stock

def register_commands(app):
    @app.cli.command("demo-data")
    @click.option("--password",prompt=True,hide_input=True,confirmation_prompt=True)
    def demo_data(password):
        """Cria dados fictícios somente quando explicitamente solicitado."""
        if User.query.first(): raise click.ClickException("O banco deve estar vazio para gerar a demonstração.")
        roles=Role.query.filter(Role.name.in_(("administrador","contador","conferente"))).all()
        user=User(name="Administrador Demonstração",username="demo",roles=roles,active=True); user.set_password(password)
        cellar=Cellar(name="Adega Demonstração",description="Dados fictícios")
        sector=Sector(cellar=cellar,code="A",name="Setor A")
        wine=Wine(name="Vinho Exemplo",producer="Produtor Fictício",country="Brasil",region="Serra Gaúcha",type="Tinto",grape="Merlot",vintage=2022,volume_ml=750)
        db.session.add_all([user,cellar,sector,wine]); db.session.flush()
        positions=[Position(sector=sector,cellar_id=cellar.id,code=f"A{i:02}",description=f"Prateleira {i}") for i in range(1,4)]
        db.session.add_all(positions); db.session.flush()
        adjust_stock(positions[0],wine,12,user,"Carga de demonstração",commit=False); db.session.commit()
        click.echo("Dados fictícios criados. Usuário: demo")
