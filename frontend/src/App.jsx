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
import FichaCliente from './gestoria/FichaCliente.jsx'
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
            <Route path="/clientes/:id" element={<FichaCliente />} />
            <Route path="/albaranes" element={<Albaranes />} />
            <Route path="/ventas-tpv" element={<Tpv />} />
            <Route path="/compras" element={<Facturas tipo="compras" />} />
            <Route path="/ventas" element={<Facturas tipo="ventas" />} />
            <Route path="/conciliacion" element={<Conciliacion />} />
            <Route path="/contabilidad" element={<Contabilidad />} />
            <Route path="/iva" element={<Iva />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </Sesion.Provider>
  )
}
