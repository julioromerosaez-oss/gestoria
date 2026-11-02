"""Se ejecuta en un proceso aparte (la config se lee al importar)."""
import time
import uuid

import jwt
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.routers import auth as rauth
from app.models import Rol, Usuario

Base.metadata.create_all(engine)
uid = str(uuid.uuid4())
db = SessionLocal()
db.add(Usuario(auth_uid=uid, email="g@s.es", nombre="G", rol=Rol.gestor))
db.commit()
S = "supersecreto-de-prueba-32-caracteres-min"


def tk(**kw):
    p = {"sub": uid, "aud": "authenticated", "iss": "https://abc.supabase.co/auth/v1",
         "exp": int(time.time()) + 600}
    p.update(kw)
    return {"Authorization": "Bearer " + jwt.encode(p, S, algorithm="HS256")}


# Simula Supabase Auth (el backend es quien lo llama; el navegador nunca)
def falso_login(email, password):
    if password != "buena":
        return None
    return {"access_token": jwt.encode({"sub": uid, "aud": "authenticated", "iss": "https://abc.supabase.co/auth/v1",
            "exp": int(time.time()) + 600}, S, algorithm="HS256"), "refresh_token": "rt-1", "expires_in": 600,
            "user": {"id": uid}}
def falso_refresh(rt):
    return falso_login("", "buena") if rt == "rt-1" else None
rauth.supabase_login_password = falso_login
rauth.supabase_refresh = falso_refresh
rauth.supabase_logout = lambda t: None

with TestClient(app) as c:
    r = c.post("/api/auth/login", json={"email": "g@s.es", "password": "buena"})
    assert r.status_code == 200 and r.json()["refresh_token"] == "rt-1", r.text
    assert c.get("/api/clientes", headers={"Authorization": "Bearer " + r.json()["token"]}).status_code == 200
    assert c.post("/api/auth/login", json={"email": "g@s.es", "password": "mala"}).status_code == 401
    assert c.post("/api/auth/refresh", json={"refresh_token": "rt-1"}).status_code == 200
    assert c.post("/api/auth/refresh", json={"refresh_token": "robado"}).status_code == 401
    assert c.get("/api/auth/yo", headers=tk()).status_code == 200
    assert c.get("/api/auth/yo", headers=tk(exp=int(time.time()) - 10)).status_code == 401
    assert c.get("/api/auth/yo", headers=tk(aud="anon")).status_code == 401
    assert c.get("/api/auth/yo", headers=tk(iss="https://evil.supabase.co/auth/v1")).status_code == 401
    assert c.get("/api/auth/yo", headers=tk(sub=str(uuid.uuid4()))).status_code == 403
print("OK")
