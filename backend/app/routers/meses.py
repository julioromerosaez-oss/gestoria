"""Ficha de cliente por mes y por proveedor (gestoría): resumen, qué falta, liquidación."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import auditar, solo_gestor
from ..db import get_db
from ..models import Cliente, Usuario
from ..schemas import AlbaranOut, FacturaCompraOut
from ..services import cierres

router = APIRouter(prefix="/api/clientes/{cliente_id}", tags=["ficha cliente"], dependencies=[Depends(solo_gestor)])


class LiquidarIn(BaseModel):
    forzar: bool = False


def _cliente(db: Session, cliente_id: int) -> Cliente:
    c = db.get(Cliente, cliente_id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


def _mes_ok(mes: int):
    if not 1 <= mes <= 12:
        raise HTTPException(422, "Mes 1-12")


@router.get("/meses")
def meses(cliente_id: int, anio: int, db: Session = Depends(get_db)):
    _cliente(db, cliente_id)
    return cierres.meses_del_anio(db, cliente_id, anio)


@router.get("/meses/{anio}/{mes}")
def mes(cliente_id: int, anio: int, mes: int, db: Session = Depends(get_db)):
    _cliente(db, cliente_id)
    _mes_ok(mes)
    return {"resumen": cierres.resumen(db, cliente_id, anio, mes),
            "pendientes": cierres.pendientes(db, cliente_id, anio, mes)}


@router.post("/meses/{anio}/{mes}/liquidar")
def liquidar(cliente_id: int, anio: int, mes: int, datos: LiquidarIn, request: Request,
             db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    _cliente(db, cliente_id)
    _mes_ok(mes)
    informe = cierres.liquidar(db, cliente_id, anio, mes, gestor, datos.forzar)
    auditar(db, request, gestor, "liquidar_mes", "cliente", cliente_id,
            f"{mes:02d}/{anio}, {informe['asientos_generados']} asientos" + (" (forzado)" if datos.forzar else ""))
    db.commit()
    return informe


@router.get("/meses/{anio}/{mes}/informe")
def informe(cliente_id: int, anio: int, mes: int, db: Session = Depends(get_db)):
    c = cierres.cierre(db, cliente_id, anio, mes)
    if not c or not c.resumen or c.estado.value != "liquidado":
        raise HTTPException(404, "El mes no está liquidado")
    return json.loads(c.resumen)


@router.post("/meses/{anio}/{mes}/reabrir")
def reabrir(cliente_id: int, anio: int, mes: int, request: Request, db: Session = Depends(get_db),
            gestor: Usuario = Depends(solo_gestor)):
    _cliente(db, cliente_id)
    cierres.reabrir(db, cliente_id, anio, mes)
    auditar(db, request, gestor, "reabrir_mes", "cliente", cliente_id, f"{mes:02d}/{anio}")
    db.commit()
    return {"estado": "abierto"}


@router.get("/proveedores")
def proveedores(cliente_id: int, anio: int, db: Session = Depends(get_db)):
    _cliente(db, cliente_id)
    return cierres.proveedores(db, cliente_id, anio)


@router.get("/proveedores/documentos")
def documentos_proveedor(cliente_id: int, clave: str, anio: int, db: Session = Depends(get_db)):
    d = cierres.documentos_proveedor(db, cliente_id, clave, anio)
    return {"facturas": [FacturaCompraOut.model_validate(f).model_dump(mode="json") for f in d["facturas"]],
            "albaranes": [AlbaranOut.model_validate(a).model_dump(mode="json") for a in d["albaranes"]]}
