import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { logout as apiLogout, usuarioActual } from './api'
import Login from './Login.jsx'
import Layout from './gestoria/Layout.jsx'
import Panel from './gestoria/Panel.jsx'
import Clientes from './gestoria/Clientes.jsx'
import Facturas from './gestoria/Facturas.jsx'
import Conciliacion from './gestoria/Conciliacion.jsx'
import Contabilidad from './gestoria/Contabilidad.jsx'
import Iva from './gestoria/Iva.jsx'
import Albaranes from './gestoria/Albaranes.jsx'
import Tpv from './gestoria/Tpv.jsx'
import ClienteLayout, { ClienteResumen } from './gestoria/ClienteLayout.jsx'
import ClienteProveedores from './gestoria/ClienteProveedores.jsx'
import { ClienteDatos } from './gestoria/Clientes.jsx'
import { useOutletContext } from 'react-router-dom'
import MovilApp from './movil/MovilApp.jsx'

const Sesion = createContext(null)
export const useSesion = () => useContext(Sesion)

export default function App() {
  const [usuario, setUsuario] = useState(undefined)
  const loc = useLocation()

  useEffect(() => {
    usuarioActual().then(setUsuario).catch(() => setUsuario(null))
    const caducada = () => setUsuario(null)
    window.addEventListener('sesion-caducada', caducada)
    return () => window.removeEventListener('sesion-caducada', caducada)
  }, [])

  const salir = async () => { await apiLogout(); setUsuario(null) }
  const esMovil = loc.pathname.startsWith('/movil')

  if (usuario === undefined) return <div className="cargando">Cargando…</div>
  if (!usuario) return <Login movil={esMovil} onLogin={setUsuario} />

  return (
    <Sesion.Provider value={{ usuario, salir }}>
      {usuario.rol !== 'gestor' ? (
        <Routes>
          <Route path="/movil/*" element={<MovilApp />} />
          <Route path="*" element={<Navigate to="/movil" replace />} />
        </Routes>
      ) : (
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Panel />} />
            <Route path="/clientes" element={<Clientes />} />
            <Route path="/clientes/:id" element={<ClienteLayout />}>
              <Route index element={<ClienteResumen />} />
              <Route path="compras" element={<FacturasMes tipo="compras" />} />
              <Route path="albaranes" element={<AlbaranesMes />} />
              <Route path="ventas" element={<FacturasMes tipo="ventas" />} />
              <Route path="caja" element={<TpvMes />} />
              <Route path="proveedores" element={<ClienteProveedores />} />
              <Route path="banco" element={<Conciliacion />} />
              <Route path="contabilidad" element={<Contabilidad />} />
              <Route path="iva" element={<Iva />} />
              <Route path="datos" element={<ClienteDatos />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </Sesion.Provider>
  )
}

// Secciones del cliente que trabajan con el mes elegido en la cabecera
function rango(anio, mes) {
  const m = String(mes).padStart(2, '0')
  return { desde: `${anio}-${m}-01`, hasta: `${anio}-${m}-${new Date(anio, mes, 0).getDate()}` }
}
function FacturasMes({ tipo }) {
  const { clienteId, anio, mes } = useOutletContext()
  return <Facturas key={tipo} tipo={tipo} clienteFijo={clienteId} {...rango(anio, mes)} embebido />
}
function AlbaranesMes() {
  const { clienteId, anio, mes } = useOutletContext()
  return <Albaranes clienteFijo={clienteId} anioFijo={anio} mesFijo={mes} embebido />
}
function TpvMes() {
  const { clienteId, anio, mes } = useOutletContext()
  return <Tpv clienteFijo={clienteId} anioFijo={anio} mesFijo={mes} embebido />
}
