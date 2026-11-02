import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import { Estado, NOMBRES_MES } from '../comun.jsx'
import { CampanaIva } from './Iva.jsx'

const SECCION = { compras: 'compras', ventas: 'ventas', albaranes: 'albaranes', 'ventas-tpv': 'caja' }
const TIPO = { compra: 'Factura de compra', venta: 'Factura de venta', albaran: 'Albarán', tpv: 'Cierre de caja' }

/** Visión de toda la gestoría: qué clientes necesitan atención y qué documentos hay que revisar. */
export default function Panel() {
  const [p, setP] = useState(null)
  const { clientes } = useOutletContext()
  const nav = useNavigate()
  useEffect(() => { api('/api/panel').then(setP) }, [])
  const hoy = new Date()
  const mesAnterior = NOMBRES_MES[(hoy.getMonth() + 11) % 12].toLowerCase()
  const atencion = clientes.filter((c) => c.activo && (c.pendientes || c.sin_conciliar || c.estado_mes_anterior !== 'liquidado'))
    .sort((a, b) => (b.pendientes + b.sin_conciliar) - (a.pendientes + a.sin_conciliar))
  const revisar = (s) => {
    const mes = (s.fecha || hoy.toISOString()).slice(0, 7)
    nav(`/clientes/${s.cliente_id}/${SECCION[s.ruta]}?mes=${mes}&abrir=${s.id}`)
  }
  if (!p) return <p className="cargando">Cargando…</p>
  const kpis = [
    ['Clientes activos', p.clientes],
    ['Documentos por revisar', p.compras_pendientes + p.ventas_pendientes + p.albaranes_pendientes + p.tpv_pendientes],
    ['Albaranes sin factura', p.albaranes_sin_factura],
    ['Revisados por contabilizar', p.por_contabilizar],
    ['Movimientos sin conciliar', p.movimientos_sin_conciliar],
  ]
  return (
    <>
      <h1>Panel</h1>
      <div className="kpis">
        {kpis.map(([t, v]) => <div key={t} className="kpi"><span className="kpi__valor">{v}</span><span className="kpi__titulo">{t}</span></div>)}
      </div>
      <div className="dos-columnas">
        <section className="tarjeta">
          <h2>Clientes que necesitan atención</h2>
          {atencion.length === 0 ? <p className="ok">✓ Todos los clientes al día.</p> : (
            <table className="tabla clicable">
              <thead><tr><th>Cliente</th><th>Por revisar</th><th>Banco</th><th>Cierre de {mesAnterior}</th></tr></thead>
              <tbody>{atencion.map((c) => (
                <tr key={c.id} onClick={() => nav(`/clientes/${c.id}`)}>
                  <td><strong>{c.razon_social}</strong></td>
                  <td>{c.pendientes ? <span className="estado estado--pendiente">◷ {c.pendientes}</span> : '—'}</td>
                  <td>{c.sin_conciliar || '—'}</td>
                  <td><Estado estado={c.estado_mes_anterior} /></td>
                </tr>))}
              </tbody>
            </table>
          )}
        </section>
        <section className="tarjeta">
          <h2>Últimos documentos por revisar</h2>
          {p.ultimas_subidas_movil.length === 0 ? <p className="vacio">No hay documentos pendientes.</p> : (
            <ul className="lista-docs">
              {p.ultimas_subidas_movil.map((s) => (
                <li key={`${s.tipo}${s.id}`}>
                  <button onClick={() => revisar(s)}>
                    <span><strong>{TIPO[s.tipo]}{s.tercero ? ` · ${s.tercero}` : ''}</strong>
                      <small>{s.cliente} · subido {new Date(s.creado_en).toLocaleDateString('es-ES')}{s.notas ? ` · “${s.notas}”` : ''}</small></span>
                    {s.confianza && <span className={`etiqueta etiqueta--${s.confianza}`}>lectura {s.confianza}</span>}
                    <span className="flecha" aria-hidden>›</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <CampanaIva />
    </>
  )
}
