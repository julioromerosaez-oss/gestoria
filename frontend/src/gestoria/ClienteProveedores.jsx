import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useSearchParams } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { Estado, Modal, NOMBRES_MES } from '../comun.jsx'
import { DetalleAlbaran } from './Albaranes.jsx'

/** Proveedores del cliente en el año del mes seleccionado: facturas, albaranes y meses con factura. */
export default function ClienteProveedores() {
  const { clienteId, anio } = useOutletContext()
  const [filas, setFilas] = useState(null)
  const [sel, setSel] = useState(null)
  const [filtro, setFiltro] = useState('')
  useEffect(() => { setFilas(null); api(`/api/clientes/${clienteId}/proveedores?anio=${anio}`).then(setFilas) }, [clienteId, anio])
  const vis = (filas || []).filter((f) => `${f.proveedor_nombre} ${f.proveedor_nif}`.toLowerCase().includes(filtro.toLowerCase()))
  return (
    <>
      <div className="barra-mes">
        <input className="buscar" placeholder="Buscar proveedor" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        <span className="ayuda">Todo {anio}: facturas revisadas y albaranes. Pulsa un proveedor para ver sus documentos.</span>
      </div>
      {filas === null ? <p className="cargando">Cargando…</p> : (
        <table className="tabla tarjeta clicable">
          <thead><tr><th>Proveedor</th><th className="num">Facturas</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th>
            <th className="num">Albaranes</th><th>Sin factura</th><th>Meses con factura</th><th>Por revisar</th></tr></thead>
          <tbody>
            {vis.map((f) => (
              <tr key={f.clave} onClick={() => setSel(f)}>
                <td><strong>{f.proveedor_nombre || '—'}</strong><br /><small>{f.proveedor_nif}</small></td>
                <td className="num">{f.facturas}</td><td className="num">{eur(f.base)}</td><td className="num">{eur(f.iva)}</td><td className="num">{eur(f.total)}</td>
                <td className="num">{f.albaranes ? `${f.albaranes} · ${eur(f.albaranes_base)}` : '—'}</td>
                <td>{f.albaranes_sin_factura ? <span className="estado estado--pendiente">{f.albaranes_sin_factura} albaranes</span> : '—'}</td>
                <td><span className="mini-meses">{Array.from({ length: 12 }, (_, i) => <i key={i} className={f.meses.includes(i + 1) ? 'si' : ''} title={NOMBRES_MES[i]} />)}</span></td>
                <td>{f.pendientes ? <span className="estado estado--pendiente">{f.pendientes}</span> : '—'}</td>
              </tr>))}
            {vis.length === 0 && <tr><td colSpan={9} className="vacio">Sin proveedores en {anio}.</td></tr>}
          </tbody>
        </table>
      )}
      {sel && <DocsProveedor clienteId={clienteId} anio={anio} prov={sel} onCerrar={() => setSel(null)} />}
    </>
  )
}

function DocsProveedor({ clienteId, anio, prov, onCerrar }) {
  const [d, setD] = useState(null)
  const [alb, setAlb] = useState(null)
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const cargar = () => api(`/api/clientes/${clienteId}/proveedores/documentos?anio=${anio}&clave=${encodeURIComponent(prov.clave)}`).then(setD)
  useEffect(() => { cargar() }, [])
  const abrirFactura = (f) => {
    const n = new URLSearchParams(sp)
    n.set('abrir', f.id)
    if (f.fecha) n.set('mes', f.fecha.slice(0, 7))
    nav(`/clientes/${clienteId}/compras?${n}`)
  }
  return (
    <Modal titulo={`${prov.proveedor_nombre || prov.proveedor_nif} · ${anio}`} onCerrar={onCerrar} ancho="900px">
      {!d ? <p className="cargando">Cargando…</p> : (
        <div className="dos-columnas">
          <div>
            <h3>Facturas ({d.facturas.length})</h3>
            <table className="tabla clicable"><tbody>{d.facturas.map((f) => (
              <tr key={f.id} onClick={() => abrirFactura(f)}><td>{fecha(f.fecha)}</td><td>{f.numero}</td><td className="num">{eur(f.total)}</td><td><Estado estado={f.estado} /></td></tr>))}
            </tbody></table>
          </div>
          <div>
            <h3>Albaranes ({d.albaranes.length})</h3>
            <table className="tabla clicable"><tbody>{d.albaranes.map((a) => (
              <tr key={a.id} onClick={() => setAlb(a)}><td>{fecha(a.fecha)}</td><td>{a.numero}</td><td className="num">{eur(a.base_imponible)}</td><td><Estado estado={a.estado} /></td></tr>))}
            </tbody></table>
          </div>
        </div>
      )}
      {alb && <DetalleAlbaran inicial={alb} onCerrar={() => setAlb(null)} onCambio={cargar} />}
    </Modal>
  )
}
