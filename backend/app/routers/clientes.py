from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config
from ..auth import auditar, crear_usuario_supabase, hash_password, solo_gestor
from ..db import get_db
from ..models import ROLES_CLIENTE, Cliente, EstadoFactura, FacturaCompra, FacturaVenta, Usuario
from ..schemas import AccesoMovilIn, ClienteIn, ClienteOut, UsuarioOut

router = APIRouter(prefix="/api/clientes", tags=["clientes"], dependencies=[Depends(solo_gestor)])


def _pendientes(db: Session) -> dict[int, int]:
    cuenta: dict[int, int] = {}
    for modelo in (FacturaCompra, FacturaVenta):
        for cid, n in db.execute(select(modelo.cliente_id, func.count())
                                 .where(modelo.estado == EstadoFactura.pendiente)
                                 .group_by(modelo.cliente_id)):
            cuenta[cid] = cuenta.get(cid, 0) + n
    return cuenta


@router.get("", response_model=list[ClienteOut])
def listar(q: str | None = None, db: Session = Depends(get_db)):
    consulta = select(Cliente).order_by(Cliente.razon_social)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Cliente.razon_social.ilike(patron) | Cliente.nif.ilike(patron))
    pend = _pendientes(db)
    return [ClienteOut.model_validate(c).model_copy(update={"pendientes": pend.get(c.id, 0)})
            for c in db.scalars(consulta)]


@router.post("", response_model=ClienteOut, status_code=201)
def crear(datos: ClienteIn, request: Request, db: Session = Depends(get_db),
          gestor: Usuario = Depends(solo_gestor)):
    cliente = Cliente(**datos.model_dump() | {"nif": datos.nif.strip().upper()})
    db.add(cliente)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un cliente con ese NIF")
    auditar(db, request, gestor, "crear", "cliente", cliente.id)
    db.commit()
    return cliente


def _obtener(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    return cliente


@router.get("/{cliente_id}", response_model=ClienteOut)
def detalle(cliente_id: int, db: Session = Depends(get_db)):
    return _obtener(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteOut)
def actualizar(cliente_id: int, datos: ClienteIn, request: Request, db: Session = Depends(get_db),
               gestor: Usuario = Depends(solo_gestor)):
    cliente = _obtener(db, cliente_id)
    for k, v in datos.model_dump().items():
        setattr(cliente, k, v)
    cliente.nif = cliente.nif.strip().upper()
    try:
        auditar(db, request, gestor, "editar", "cliente", cliente.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un cliente con ese NIF")
    return cliente


@router.get("/{cliente_id}/usuarios", response_model=list[UsuarioOut])
def usuarios(cliente_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(Usuario).where(Usuario.cliente_id == cliente_id)).all()


@router.post("/{cliente_id}/usuarios", response_model=UsuarioOut, status_code=201)
def crear_acceso_movil(cliente_id: int, datos: AccesoMovilIn, request: Request,
                       db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    """Da de alta el acceso a la web app móvil para un usuario del cliente."""
    _obtener(db, cliente_id)
    if datos.rol not in ROLES_CLIENTE:
        raise HTTPException(422, "Rol no válido para un usuario de cliente")
    email = datos.email.strip().lower()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise HTTPException(409, "Ya existe un usuario con ese email")
    usuario = Usuario(email=email, nombre=datos.nombre, rol=datos.rol, cliente_id=cliente_id)
    if config.AUTH_MODO == "supabase":
        usuario.auth_uid = crear_usuario_supabase(email, datos.password, datos.nombre)
    else:
        usuario.password_hash = hash_password(datos.password)
    db.add(usuario)
    db.flush()
    auditar(db, request, gestor, "alta_acceso_movil", "cliente", cliente_id, f"{email} ({datos.rol.value})")
    db.commit()
    return usuario
