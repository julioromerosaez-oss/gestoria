import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'

export default function Panel() {
  const [p, setP] = useState(null)
  const { setClienteId } = useOutletContext()
  const nav = useNavigate()
  useEffect(() => { api('/api/panel').then(setP) }, [])
  if (!p) return <p className="cargando">Cargando…</p>
  const kpis = [
    ['Clientes activos', p.clientes, '/clientes'],
    ['Subidas pendientes', p.compras_pendientes + p.ventas_pendientes + p.albaranes_pendientes + p.tpv_pendientes, '/compras'],
    ['Albaranes sin factura', p.albaranes_sin_factura, '/albaranes'],
    ['Por contabilizar', p.por_contabilizar, '/compras'],
    ['Movimientos sin conciliar', p.movimientos_sin_conciliar, '/conciliacion'],
  ]
  return (
    <>
      <h1>Panel</h1>
      <div className="kpis">
        {kpis.map(([t, v, to]) => (
          <Link key={t} to={to} className="kpi"><span className="kpi__valor">{v}</span><span className="kpi__titulo">{t}</span></Link>
        ))}
      </div>
      <section className="tarjeta">
        <h2>Documentos subidos por los clientes pendientes de revisar</h2>
        {p.ultimas_subidas_movil.length === 0 ? <p className="vacio">No hay subidas pendientes.</p> : (
          <table className="tabla">
            <thead><tr><th>Cliente</th><th>Documento</th><th>Subida</th><th>Lectura</th><th>Nota</th><th /></tr></thead>
            <tbody>
              {p.ultimas_subidas_movil.map((s) => (
                <tr key={s.id}>
                  <td>{s.cliente}</td>
                  <td>{{ compra: 'Factura de compra', venta: 'Factura de venta', albaran: 'Albarán', tpv: 'Cierre de caja' }[s.tipo]}{s.tercero ? ` · ${s.tercero}` : ''}</td>
                  <td>{new Date(s.creado_en).toLocaleString('es-ES')}</td>
                  <td>{s.confianza ? <span className={`etiqueta etiqueta--${s.confianza}`}>{s.confianza}</span> : '—'}</td>
                  <td>{s.notas || '—'}</td>
                  <td><button className="btn btn--secundario btn--peq" onClick={() => { setClienteId(s.cliente_id); nav(`/${s.ruta}?abrir=${s.id}`) }}>Revisar</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}
