from app import config


def test_clave_nueva_solo_en_apikey():
    # las claves sb_secret_ no son JWT: si van en Authorization: Bearer, Supabase las rechaza
    assert config.cabeceras_supabase("sb_secret_abc123") == {"apikey": "sb_secret_abc123"}


def test_clave_antigua_jwt_en_las_dos_cabeceras():
    jwt = "eyJhbGciOiJIUzI1NiJ9.e30.x"
    assert config.cabeceras_supabase(jwt) == {"apikey": jwt, "Authorization": f"Bearer {jwt}"}
