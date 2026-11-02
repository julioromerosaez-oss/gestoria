import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_validacion_jwt_supabase():
    env = os.environ | {
        "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/sb.db", "AUTH_MODO": "supabase",
        "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "x",
        "SUPABASE_JWT_SECRET": "supersecreto-de-prueba-32-caracteres-min", "STORAGE_MODO": "local",
        "SERVIR_FRONTEND": "0", "UPLOAD_DIR": tempfile.mkdtemp()}
    raiz = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(raiz / "tests/scripts/supabase_jwt.py")], cwd=raiz,
                       env=env | {"PYTHONPATH": str(raiz)}, capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
