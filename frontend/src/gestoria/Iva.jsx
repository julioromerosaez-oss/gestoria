import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api, eur, trimestreActual } from '../api'
import { GraficoMargen } from '../comun.jsx'

export function Liquidacion({ liq }) {
  return (
    <div className="liquidacion">
      <div className={`resultado resultado--${liq.resultado > 0 ? 'ingresar' : 'compensar'}`}>
        <span>Resultado {liq.periodo}</span>
        <strong>{eur(Math.abs(liq.resultado))}</strong>
        <span>{liq.situacion} · plazo {liq.plazo_presentacion}</span>
      </div>
      {liq.facturas_pendientes_revision > 0 && <p className="aviso">Hay {liq.facturas_pendientes_revision} facturas pendientes de revisar que aún no cuentan.</p>}
      <div className="dos-columnas">
        {[['IVA repercutido (ventas)', liq.repercutido, liq.total_repercutido], ['IVA soportado deducible (compras)', liq.soportado, liq.total_soportado]].map(([t, filas, total]) => (
          <table key={t} className="tabla">
            <caption>{t}</caption>
            <thead><tr><th>Tipo</th><th className="num">Facturas</th><th className="num">Base</th><th className="num">Cuota</th></tr></thead>
            <tbody>{filas.map((r) => <tr key={r.tipo}><td>{r.tipo} %</td><td className="num">{r.facturas}</td><td className="num">{eur(r.base)}</td><td className="num">{eur(r.cuota)}</td></tr>)}
              {filas.length === 0 && <tr><td colSpan={4} className="vacio">Sin facturas</td></tr>}</tbody>
            <tfoot><tr><td colSpan={3}>Total cuotas</td><td className="num">{eur(total)}</td></tr></tfoot>
          </table>
        ))}
      </div>
    </div>
  )
}

export default function Iva() {
  const { clienteId, setClienteId } = useOutletContext()
  const [p, setP] = useState(trimestreActual())
  const [liq, setLiq] = useState(null)
  const [margen, setMargen] = useState(null)
  const [todos, setTodos] = useState([])

  useEffect(() => {
    if (clienteId) {
      api(`/api/iva/liquidacion?cliente_id=${clienteId}&anio=${p.anio}&trimestre=${p.trimestre}`).then(setLiq)
      api(`/api/margen?cliente_id=${clienteId}&anio=${p.anio}`).then(setMargen)
    } else {
      api(`/api/iva/resumen?anio=${p.anio}&trimestre=${p.trimestre}`).then(setTodos)
    }
  }, [clienteId, p.anio, p.trimestre])

  return (
    <>
      <div className="cabecera">
        <h1>IVA y margen</h1>
        <div className="acciones">
          <select value={p.trimestre} onChange={(e) => setP({ ...p, trimestre: Number(e.target.value) })} aria-label="Trimestre">
            {[1, 2, 3, 4].map((t) => <option key={t} value={t}>{t}º trimestre</option>)}
          </select>
          <select value={p.anio} onChange={(e) => setP({ ...p, anio: Number(e.target.value) })} aria-label="Año">
            {[0, 1, 2].map((i) => { const a = new Date().getFullYear() - i; return <option key={a}>{a}</option> })}
          </select>
        </div>
      </div>
      {!clienteId ? (
        <section className="tarjeta">
          <h2>Campaña de IVA · {p.trimestre}T {p.anio}</h2>
          <table className="tabla clicable">
            <thead><tr><th>Cliente</th><th>NIF</th><th className="num">Repercutido</th><th className="num">Soportado</th><th className="num">Resultado</th><th>Situación</th><th>Pendientes</th></tr></thead>
            <tbody>{todos.map((l) => (
              <tr key={l.cliente_id} onClick={() => setClienteId(l.cliente_id)}>
                <td>{l.razon_social}</td><td>{l.nif}</td><td className="num">{eur(l.total_repercutido)}</td>
                <td className="num">{eur(l.total_soportado)}</td><td className="num"><strong>{eur(l.resultado)}</strong></td>
                <td>{l.situacion}</td><td>{l.facturas_pendientes_revision ? <span className="estado estado--pendiente">{l.facturas_pendientes_revision}</span> : '—'}</td>
              </tr>))}</tbody>
          </table>
        </section>
      ) : (
        <>
          {liq && <section className="tarjeta"><h2>Liquidación de IVA (modelo 303)</h2><Liquidacion liq={liq} /></section>}
          {margen && (
            <section className="tarjeta">
              <h2>Margen {p.anio}</h2>
              <div className="kpis kpis--peq">
                <div className="kpi"><span className="kpi__valor">{eur(margen.ingresos)}</span><span className="kpi__titulo">Ingresos (base)</span></div>
                <div className="kpi"><span className="kpi__valor">{eur(margen.gastos)}</span><span className="kpi__titulo">Gastos (base)</span></div>
                <div className="kpi"><span className="kpi__valor">{eur(margen.margen)}</span><span className="kpi__titulo">Margen · {margen.margen_pct.toLocaleString('es-ES')} %</span></div>
              </div>
              <GraficoMargen meses={margen.meses} />
            </section>
          )}
        </>
      )}
    </>
  )
}
