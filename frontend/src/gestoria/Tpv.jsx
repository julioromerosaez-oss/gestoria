import { useEffect, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { AvisoLectura, Cajon, Estado, SelectorMes, rangoMes } from '../comun.jsx'

/** Ventas de caja (cierres Z del TPV) de un mes. */
export default function Tpv({ clienteFijo, anioFijo, mesFijo, embebido = false }) {
  const ctx = useOutletContext()
  const clienteId = clienteFijo ?? ctx.clienteId
  const hoy = new Date()
  const [p, setP] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1 })
  const anio = anioFijo ?? p.anio, mes = mesFijo ?? p.mes
  const [filas, setFilas] = useState([])
  const [abierto, setAbierto] = useState(null)
  const [params, setParams] = useSearchParams()
  const cargar = () => {
    if (!clienteId) return
    const { desde, hasta } = rangoMes(anio, mes)
    api(`/api/ventas-tpv?cliente_id=${clienteId}&desde=${desde}&hasta=${hasta}`).then(setFilas)
  }
  useEffect(cargar, [clienteId, anio, mes])
  useEffect(() => {
    const id = params.get('abrir')
    if (id) { api(`/api/ventas-tpv/${id}`).then(setAbierto); const n = new URLSearchParams(params); n.delete('abrir'); setParams(n, { replace: true }) }
  }, [params])
  if (!clienteId) return <><h1>Ventas de caja</h1><p className="vacio tarjeta">Selecciona un cliente arriba.</p></>
  const tot = filas.filter((f) => f.estado !== 'rechazada').reduce((a, f) => ({ base: a.base + f.base_imponible, iva: a.iva + f.cuota_iva, total: a.total + f.total, ef: a.ef + f.cobro_efectivo, tj: a.tj + f.cobro_tarjeta }), { base: 0, iva: 0, total: 0, ef: 0, tj: 0 })
  return (
    <>
      {!embebido && <div className="cabecera"><h1>Ventas de caja (TPV)</h1><SelectorMes anio={anio} mes={mes} onCambio={(a, m) => setP({ anio: a, mes: m })} /></div>}
      <div className="resumen-linea"><span>{filas.length} cierres</span><span>Base {eur(tot.base)}</span><span>IVA {eur(tot.iva)}</span>
        <span>Total {eur(tot.total)}</span><span>Efectivo {eur(tot.ef)}</span><span>Tarjeta {eur(tot.tj)}</span></div>
      <table className="tabla tarjeta clicable">
        <thead><tr><th>Fecha</th><th>Z</th><th className="num">Tickets</th><th>Tipos IVA</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th><th className="num">Efectivo</th><th className="num">Tarjeta</th><th>Estado</th></tr></thead>
        <tbody>
          {filas.map((v) => (
            <tr key={v.id} onClick={() => setAbierto(v)}>
              <td>{fecha(v.fecha)}</td><td>{v.numero_z || '—'}</td><td className="num">{v.num_tickets ?? '—'}</td>
              <td>{v.desglose.map((d) => `${d.tipo_iva}%`).join(' · ') || '—'}</td>
              <td className="num">{eur(v.base_imponible)}</td><td className="num">{eur(v.cuota_iva)}</td><td className="num">{eur(v.total)}</td>
              <td className="num">{eur(v.cobro_efectivo)}</td><td className="num">{eur(v.cobro_tarjeta)}</td>
              <td><Estado estado={v.estado} />{v.estado === 'pendiente' && v.extraccion_confianza && <span className={`etiqueta etiqueta--${v.extraccion_confianza}`}>lectura {v.extraccion_confianza}</span>}</td>
            </tr>))}
          {filas.length === 0 && <tr><td colSpan={10} className="vacio">No hay cierres de caja en este mes.</td></tr>}
        </tbody>
      </table>
      {abierto && <DetalleTpv inicial={abierto} onCerrar={() => setAbierto(null)} onCambio={cargar} />}
    </>
  )
}

function DetalleTpv({ inicial, onCerrar, onCambio }) {
  const [v, setV] = useState(inicial)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  useEffect(() => { setV(inicial) }, [inicial])
  const bloqueado = v.estado === 'contabilizada'
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })
  const setD = (i, k) => (e) => setV({ ...v, desglose: v.desglose.map((d, j) => (j === i ? { ...d, [k]: e.target.value } : d)) })
  const suma = v.desglose.reduce((s, d) => s + (Number(d.base) || 0) + (Number(d.cuota) || 0), 0)
  const datos = () => ({ fecha: v.fecha || null, numero_z: v.numero_z || null, num_tickets: v.num_tickets ? Number(v.num_tickets) : null,
    cobro_efectivo: String(v.cobro_efectivo || 0), cobro_tarjeta: String(v.cobro_tarjeta || 0), cuenta_ingreso: v.cuenta_ingreso || '700',
    notas: v.notas || null, desglose: v.desglose.map((d) => ({ tipo_iva: String(d.tipo_iva), base: String(d.base || 0), cuota: d.cuota === '' ? null : String(d.cuota) })) })
  const accion = async (fn, msg) => {
    setError(''); setOk('')
    try { const r = await fn(); if (r?.id && r.desglose) setV(r); setOk(msg); onCambio() } catch (e) { setError(e.message) }
  }
  return (
    <Cajon titulo={`Cierre de caja ${v.numero_z ? 'Z ' + v.numero_z : ''}`} estado={v.estado} onCerrar={onCerrar} imagen={v.tiene_imagen ? `/api/ventas-tpv/${v.id}/imagen` : null}>
      <div className="form rejilla">
        {v.estado === 'pendiente' && <div className="ancho"><AvisoLectura confianza={v.extraccion_confianza} avisos={v.extraccion_avisos} /></div>}
        {v.motivo_rechazo && <p className="error ancho">Rechazado: {v.motivo_rechazo}</p>}
        <label>Fecha<input type="date" value={v.fecha || ''} onChange={set('fecha')} disabled={bloqueado} /></label>
        <label>Nº de Z<input value={v.numero_z || ''} onChange={set('numero_z')} disabled={bloqueado} /></label>
        <label>Nº de tickets<input type="number" value={v.num_tickets ?? ''} onChange={set('num_tickets')} disabled={bloqueado} /></label>
        <label>Cuenta de ingreso<select value={v.cuenta_ingreso} onChange={set('cuenta_ingreso')} disabled={bloqueado}>
          <option value="700">700 · Ventas de mercaderías</option><option value="705">705 · Prestaciones de servicios</option></select></label>
        <div className="ancho">
          <table className="tabla"><thead><tr><th>IVA</th><th>Base</th><th>Cuota</th><th /></tr></thead>
            <tbody>{v.desglose.map((d, i) => (
              <tr key={i}>
                <td><select value={Number(d.tipo_iva)} onChange={setD(i, 'tipo_iva')} disabled={bloqueado}>{[21, 10, 5, 4].map((t) => <option key={t} value={t}>{t} %</option>)}</select></td>
                <td><input type="number" step="0.01" value={d.base} onChange={setD(i, 'base')} disabled={bloqueado} /></td>
                <td><input type="number" step="0.01" value={d.cuota} onChange={setD(i, 'cuota')} disabled={bloqueado} /></td>
                <td>{!bloqueado && <button className="btn btn--icono" onClick={() => setV({ ...v, desglose: v.desglose.filter((_, j) => j !== i) })} aria-label="Quitar">✕</button>}</td>
              </tr>))}
            </tbody>
            <tfoot><tr><td>{!bloqueado && <button className="btn btn--enlace" onClick={() => setV({ ...v, desglose: [...v.desglose, { tipo_iva: 10, base: '', cuota: '' }] })}>+ tipo de IVA</button>}</td>
              <td colSpan={2} className="num">Total {eur(suma)}</td><td /></tr></tfoot>
          </table>
        </div>
        <label>Cobrado en efectivo<input type="number" step="0.01" value={v.cobro_efectivo} onChange={set('cobro_efectivo')} disabled={bloqueado} /></label>
        <label>Cobrado con tarjeta<input type="number" step="0.01" value={v.cobro_tarjeta} onChange={set('cobro_tarjeta')} disabled={bloqueado} /></label>
        {Math.abs(Number(v.cobro_efectivo) + Number(v.cobro_tarjeta) - suma) > 0.1 && suma > 0 && <p className="aviso ancho">Efectivo + tarjeta ({eur(Number(v.cobro_efectivo) + Number(v.cobro_tarjeta))}) no coincide con el total ({eur(suma)}). Al contabilizar, la diferencia se lleva a caja.</p>}
        {error && <p className="error ancho" role="alert">{error}</p>}
        {ok && <p className="ok ancho">{ok}</p>}
        <div className="ancho botonera">
          {!bloqueado && <button className="btn btn--secundario" onClick={() => accion(() => api(`/api/ventas-tpv/${v.id}`, { method: 'PUT', body: datos() }), 'Guardado')}>Guardar</button>}
          {['pendiente', 'rechazada'].includes(v.estado) && <button className="btn btn--primario" onClick={() => accion(async () => {
            await api(`/api/ventas-tpv/${v.id}`, { method: 'PUT', body: datos() })
            return api(`/api/ventas-tpv/${v.id}/validar`, { method: 'POST' })
          }, 'Revisado')}>Guardar y marcar revisado</button>}
          {v.estado === 'validada' && <button className="btn btn--primario" onClick={() => accion(async () => { await api(`/api/ventas-tpv/${v.id}/contabilizar`, { method: 'POST' }); return api(`/api/ventas-tpv/${v.id}`) }, 'Asiento generado')}>Contabilizar</button>}
          {!bloqueado && v.tiene_imagen && <button className="btn btn--secundario" onClick={() => accion(() => api(`/api/ventas-tpv/${v.id}/extraer`, { method: 'POST' }), 'Leído de nuevo')}>Leer datos de la foto</button>}
          {!bloqueado && v.estado !== 'rechazada' && <button className="btn btn--peligro" onClick={() => {
            const motivo = prompt('Motivo del rechazo (lo verá el cliente):')
            if (motivo) accion(() => api(`/api/ventas-tpv/${v.id}/rechazar`, { method: 'POST', body: { motivo } }), 'Rechazado')
          }}>Rechazar</button>}
          {!bloqueado && <button className="btn btn--enlace" onClick={() => accion(async () => { await api(`/api/ventas-tpv/${v.id}`, { method: 'DELETE' }); onCerrar() }, '')}>Borrar</button>}
          {bloqueado && <span className="nota">Contabilizado en el asiento #{v.asiento_id}.</span>}
        </div>
      </div>
    </Cajon>
  )
}
