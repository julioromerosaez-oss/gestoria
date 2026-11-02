import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
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

/** IVA del trimestre del mes seleccionado + margen del año, para un cliente. */
export default function Iva() {
  const { clienteId, anio, mes } = useOutletContext()
  const trimestre = Math.floor((mes - 1) / 3) + 1
  const [liq, setLiq] = useState(null)
  const [margen, setMargen] = useState(null)
  useEffect(() => {
    api(`/api/iva/liquidacion?cliente_id=${clienteId}&anio=${anio}&trimestre=${trimestre}`).then(setLiq)
    api(`/api/margen?cliente_id=${clienteId}&anio=${anio}`).then(setMargen)
  }, [clienteId, anio, trimestre])
  return (
    <>
      {liq && <section className="tarjeta"><h2>Liquidación de IVA · {trimestre}º trimestre {anio} (modelo 303)</h2><Liquidacion liq={liq} /></section>}
      {margen && (
        <section className="tarjeta">
          <h2>Margen {anio}</h2>
          <div className="kpis kpis--peq">
            <div className="kpi"><span className="kpi__valor">{eur(margen.ingresos)}</span><span className="kpi__titulo">Ingresos (base)</span></div>
            <div className="kpi"><span className="kpi__valor">{eur(margen.gastos)}</span><span className="kpi__titulo">Gastos (base)</span></div>
            <div className="kpi"><span className="kpi__valor">{eur(margen.margen)}</span><span className="kpi__titulo">Margen · {margen.margen_pct.toLocaleString('es-ES')} %</span></div>
          </div>
          <GraficoMargen meses={margen.meses} />
        </section>
      )}
    </>
  )
}

/** Campaña de IVA: el trimestre de todos los clientes (va en el Panel). */
export function CampanaIva() {
  const { anio: a0, trimestre: t0 } = trimestreActual()
  // por defecto, el trimestre que toca presentar: el anterior al actual
  const [p, setP] = useState(t0 === 1 ? { anio: a0 - 1, trimestre: 4 } : { anio: a0, trimestre: t0 - 1 })
  const [todos, setTodos] = useState(null)
  const nav = useNavigate()
  useEffect(() => { setTodos(null); api(`/api/iva/resumen?anio=${p.anio}&trimestre=${p.trimestre}`).then(setTodos) }, [p.anio, p.trimestre])
  const mesFin = `${p.anio}-${String(p.trimestre * 3).padStart(2, '0')}`
  return (
    <section className="tarjeta">
      <div className="m-cab-seccion">
        <h2>Campaña de IVA · {p.trimestre}T {p.anio}</h2>
        <div className="acciones">
          <select value={p.trimestre} onChange={(e) => setP({ ...p, trimestre: Number(e.target.value) })} aria-label="Trimestre">
            {[1, 2, 3, 4].map((t) => <option key={t} value={t}>{t}º trimestre</option>)}
          </select>
          <select value={p.anio} onChange={(e) => setP({ ...p, anio: Number(e.target.value) })} aria-label="Año">
            {[0, 1, 2].map((i) => { const a = new Date().getFullYear() - i; return <option key={a}>{a}</option> })}
          </select>
        </div>
      </div>
      <table className="tabla clicable">
        <thead><tr><th>Cliente</th><th className="num">Repercutido</th><th className="num">Soportado</th><th className="num">Resultado</th><th>Situación</th><th>Por revisar</th><th>Plazo</th></tr></thead>
        <tbody>{(todos || []).map((l) => (
          <tr key={l.cliente_id} onClick={() => nav(`/clientes/${l.cliente_id}/iva?mes=${mesFin}`)}>
            <td><strong>{l.razon_social}</strong><br /><small>{l.nif}</small></td><td className="num">{eur(l.total_repercutido)}</td>
            <td className="num">{eur(l.total_soportado)}</td><td className="num"><strong>{eur(l.resultado)}</strong></td>
            <td>{l.situacion}</td><td>{l.facturas_pendientes_revision ? <span className="estado estado--pendiente">{l.facturas_pendientes_revision}</span> : '—'}</td>
            <td><small>{l.plazo_presentacion}</small></td>
          </tr>))}
          {todos === null && <tr><td colSpan={7} className="cargando">Cargando…</td></tr>}
        </tbody>
      </table>
    </section>
  )
}
