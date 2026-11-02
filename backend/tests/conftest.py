import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["AUTH_MODO"] = "local"
os.environ["SERVIR_FRONTEND"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cliente, Rol, Usuario  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture()
def c():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    c1 = Cliente(nif="44556677L", razon_social="Carlos Martín Ruiz")
    c2 = Cliente(nif="22222222J", razon_social="Cliente Dos")
    db.add_all([c1, c2])
    db.flush()
    db.add_all([
        Usuario(email="g@x.es", nombre="G", rol=Rol.gestor, password_hash=hash_password("gestor123")),
        Usuario(email="u1@x.es", nombre="U1", rol=Rol.cliente_admin, cliente_id=c1.id, password_hash=hash_password("cli123")),
        Usuario(email="compras@x.es", nombre="C1", rol=Rol.cliente_compras, cliente_id=c1.id, password_hash=hash_password("cli123")),
        Usuario(email="ventas@x.es", nombre="V1", rol=Rol.cliente_ventas, cliente_id=c1.id, password_hash=hash_password("cli123")),
        Usuario(email="u2@x.es", nombre="U2", rol=Rol.cliente_admin, cliente_id=c2.id, password_hash=hash_password("cli123")),
    ])
    db.commit()
    with TestClient(app) as cliente:
        yield cliente


def tok(c, email, pw):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


