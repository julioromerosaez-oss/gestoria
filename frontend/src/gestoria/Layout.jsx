import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useMatch, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useSesion } from '../App.jsx'

/** Secciones de la ficha de un cliente (ruta relativa, texto, clave del contador de avisos). */
export const SECCIONES = [
  ['', 'Resumen y qué falta', 'falta'],
  ['compras', 'Facturas de compra', 'compras'],
  ['albaranes', 'Albaranes', 'albaranes'],
  ['ventas', 'Facturas de venta', 'ventas'],
  ['caja', 'Caja (TPV)', 'tpv'],
  ['proveedores', 'Proveedores', null],
  ['banco', 'Conciliación bancaria', 'banco'],
  ['contabilidad', 'Apuntes contables', null],
  ['iva', 'IVA y margen', null],
  ['datos', 'Datos y usuarios', null],
]

export function mesDeParams(sp) {
  const v = sp.get('mes')
  if (v && /^\d{4}-\d{2}$/.test(v)) return { anio: Number(v.slice(0, 4)), mes: Number(v.slice(5)) }
  const hoy = new Date()
  return { anio: hoy.getFullYear(), mes: hoy.getMonth() + 1 }
}

export default function Layout() {
  const { usuario, salir } = useSesion()
  const [clientes, setClientes] = useState([])
  const recargarClientes = () => api('/api/clientes').then(setClientes)
  useEffect(() => { recargarClientes() }, [])

  // ¿Estamos dentro de un cliente? -> su menú aparece en el lateral
  const enCliente = useMatch('/clientes/:id/*')
  const clienteId = enCliente ? Number(enCliente.params.id) : null
  const cliente = clientes.find((c) => c.id === clienteId)
  const [sp] = useSearchParams()
  const { anio, mes } = mesDeParams(sp)
  const qs = `?mes=${anio}-${String(mes).padStart(2, '0')}`
  const loc = useLocation()
  const [avisos, setAvisos] = useState({})
  useEffect(() => {
    if (!clienteId) return
    api(`/api/clientes/${clienteId}/meses/${anio}/${mes}/contadores`).then(setAvisos).catch(() => setAvisos({}))
  }, [clienteId, anio, mes, loc.pathname, loc.key])

  return (
    <div className="app">
      <aside className="lateral">
        <div className="marca"><img src="/icon.svg" alt="" width="30" height="30" /><span>Gestoría</span></div>
        <nav>
          <NavLink to="/" end>Panel</NavLink>
          <NavLink to="/clientes" end>Clientes</NavLink>
        </nav>
        {clienteId && (
          <nav className="menu-cliente" aria-label="Menú del cliente">
            <div className="menu-cliente__cab" title={cliente?.razon_social}>
              <strong>{cliente?.razon_social || 'Cliente'}</strong>
              <small>{cliente?.nif}</small>
            </div>
            {SECCIONES.map(([ruta, txt, clave]) => (
              <NavLink key={ruta} to={`/clientes/${clienteId}${ruta ? '/' + ruta : ''}${qs}`} end>
                <span>{txt}</span>
                {clave && avisos[clave] > 0 && <span className={`insignia ${clave === 'falta' && avisos.bloquean ? 'insignia--fuerte' : ''}`}>{avisos[clave]}</span>}
              </NavLink>
            ))}
          </nav>
        )}
        <div className="lateral__pie">
          <span>{usuario.nombre}</span>
          <button className="btn btn--enlace" onClick={salir}>Cerrar sesión</button>
        </div>
      </aside>
      <main className="principal">
        <Outlet context={{ clientes, recargarClientes }} />
      </main>
    </div>
  )
}
