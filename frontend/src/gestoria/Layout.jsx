import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api'
import { useSesion } from '../App.jsx'

const MENU = [
  ['/', 'Panel'], ['/clientes', 'Clientes'],
  ['/compras', 'Facturas de compra'], ['/albaranes', 'Albaranes'], ['/ventas', 'Facturas de venta'], ['/ventas-tpv', 'Caja (TPV)'],
  ['/conciliacion', 'Conciliación bancaria'], ['/contabilidad', 'Apuntes contables'], ['/iva', 'IVA y margen'],
]

export default function Layout() {
  const { usuario, salir } = useSesion()
  const [clientes, setClientes] = useState([])
  const [clienteId, setClienteId] = useState(() => Number(localStorage.getItem('cliente_sel')) || '')
  const recargarClientes = () => api('/api/clientes').then(setClientes)

  useEffect(() => { recargarClientes() }, [])
  useEffect(() => { localStorage.setItem('cliente_sel', clienteId || '') }, [clienteId])

  const cliente = clientes.find((c) => c.id === clienteId)
  return (
    <div className="app">
      <aside className="lateral">
        <div className="marca"><img src="/icon.svg" alt="" width="30" height="30" /><span>Gestoría</span></div>
        <nav>
          {MENU.map(([to, txt]) => (
            <NavLink key={to} to={to} end={to === '/' || to === '/clientes'}>{txt}</NavLink>
          ))}
          {cliente && <NavLink to={`/clientes/${cliente.id}`} className="nav-ficha">Ficha · {cliente.razon_social.split(' (')[0]}</NavLink>}
        </nav>
        <div className="lateral__pie">
          <span>{usuario.nombre}</span>
          <button className="btn btn--enlace" onClick={salir}>Cerrar sesión</button>
        </div>
      </aside>
      <main className="principal">
        <div className="barra-cliente">
          <label>Cliente
            <select value={clienteId} onChange={(e) => setClienteId(Number(e.target.value) || '')}>
              <option value="">Todos los clientes</option>
              {clientes.map((c) => <option key={c.id} value={c.id}>{c.razon_social} · {c.nif}</option>)}
            </select>
          </label>
          {cliente?.pendientes > 0 && <span className="aviso">{cliente.pendientes} subidas pendientes de revisar</span>}
        </div>
        <Outlet context={{ clientes, clienteId, setClienteId, cliente, recargarClientes }} />
      </main>
    </div>
  )
}
