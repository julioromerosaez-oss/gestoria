import { useEffect, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { AvisoLectura, Cajon, Estado, Modal, SelectorMes } from '../comun.jsx'

const SITUACION = {
  sin_factura: { txt: 'Falta la factura del proveedor', clase: 'pendiente' },
  por_cuadrar: { txt: 'Factura recibida: falta cuadrar', clase: 'validada' },
  parcial: { txt: 'Hay albaranes sin factura', clase: 'pendiente' },
  descuadre: { txt: 'La factura no cuadra', clase: 'rechazada' },
  cuadra: { txt: 'Cuadra con la factura', clase: 'contabilizada' },
}

/** Albaranes de proveedor de un mes, agrupados por proveedor, con el cuadre contra su factura mensual. */
export default function Albaranes({ clienteFijo, anioFijo, mesFijo, embebido = false }) {
  const ctx = useOutletContext()
  const clienteId = clienteFijo ?? ctx.clienteId
  const hoy = new Date()
  const [p, setP] = useState({ anio: anioFijo ?? hoy.getFullYear(), mes: mesFijo ?? hoy.getMonth() + 1 })
  const anio = anioFijo ?? p.anio, mes = mesFijo ?? p.mes
  const [grupos, setGrupos] = useState([])
  const [abiertos, setAbiertos] = useState({})
  const [abierto, setAbierto] = useState(null)
  const [cuadrar, setCuadrar] = useState(null)
  const [params, setParams] = useSearchParams()
  const [sinFecha, setSinFecha] = useState([])

  const cargar = () => clienteId && api(`/api/albaranes/resumen?cliente_id=${clienteId}&anio=${anio}&mes=${mes}`).then(async (gs) => {
    const det = await api(`/api/albaranes?cliente_id=${clienteId}&anio=${anio}&mes=${mes}`)
    setGrupos(gs.map((g) => ({ ...g, filas: det.filter((a) => g.albaranes.includes(a.id)) })))
    // albaranes cuya fecha no se pudo leer: no caen en ningún mes hasta que se revisan
    setSinFecha((await api(`/api/albaranes?cliente_id=${clienteId}&estado=pendiente`)).filter((a) => !a.fecha))
  })
  useEffect(() => { cargar() }, [clienteId, anio, mes])
  useEffect(() => {
    const id = params.get('abrir')
    if (id) { api(`/api/albaranes/${id}`).then(setAbierto); const n = new URLSearchParams(params); n.delete('abrir'); setParams(n, { replace: true }) }
  }, [params])

  if (!clienteId) return <><h1>Albaranes</h1><p className="vacio tarjeta">Selecciona un cliente arriba.</p></>
  return (
    <>
      {!embebido && (
        <div className="cabecera">
          <h1>Albaranes de proveedor</h1>
          <SelectorMes anio={anio} mes={mes} onCambio={(a, m) => setP({ anio: a, mes: m })} />
        </div>
      )}
      <p className="ayuda">Los albaranes no cuentan para el IVA ni la contabilidad: solo la factura mensual del proveedor. Aquí se comprueba que la factura cuadra con la suma de sus albaranes (por base imponible).</p>
      {grupos.length === 0 && <p className="vacio tarjeta">No hay albaranes en este mes.</p>}
      {grupos.map((g) => {
        const s = SITUACION[g.situacion]
        const abiertoG = abiertos[g.clave] ?? g.situacion !== 'cuadra'
        return (
          <section key={g.clave} className="tarjeta grupo-albaranes">
            <header onClick={() => setAbiertos({ ...abiertos, [g.clave]: !abiertoG })}>
              <div>
                <strong>{g.proveedor_nombre || 'Proveedor sin identificar'}</strong>
                <small>{g.proveedor_nif || 'sin NIF'} · {g.n_albaranes} albarán(es) · {eur(g.suma_base)}</small>
              </div>
              {g.pendientes_revision > 0 && <span className="estado estado--pendiente">◷ {g.pendientes_revision} por revisar</span>}
              <span className={`estado estado--${s.clase}`}>{s.txt}{g.diferencia ? ` (${eur(g.diferencia)})` : ''}</span>
              {g.situacion !== 'cuadra' && (
                <button className="btn btn--primario btn--peq" onClick={(e) => { e.stopPropagation(); setCuadrar(g) }}>Cuadrar con factura</button>
              )}
            </header>
            {abiertoG && (
              <table className="tabla clicable">
                <thead><tr><th>Fecha</th><th>Nº albarán</th><th className="num">Base</th><th>Estado</th><th>Factura</th></tr></thead>
                <tbody>{g.filas.map((a) => (
                  <tr key={a.id} onClick={() => setAbierto(a)}>
                    <td>{fecha(a.fecha)}</td><td>{a.numero || '—'}</td><td className="num">{eur(a.base_imponible)}</td>
                    <td><Estado estado={a.estado} />{a.estado === 'pendiente' && a.extraccion_confianza && <span className={`etiqueta etiqueta--${a.extraccion_confianza}`}>lectura {a.extraccion_confianza}</span>}</td>
                    <td>{a.factura_compra_id ? g.facturas.find((f) => f.id === a.factura_compra_id)?.numero || `#${a.factura_compra_id}` : '—'}</td>
                  </tr>))}
                </tbody>
              </table>
            )}
          </section>
        )
      })}
      {sinFecha.length > 0 && (
        <section className="tarjeta grupo-albaranes">
          <header><div><strong>Sin fecha legible</strong><small>Revísalos para asignarlos a su mes</small></div></header>
          <table className="tabla clicable"><tbody>{sinFecha.map((a) => (
            <tr key={a.id} onClick={() => setAbierto(a)}><td>Subido {new Date(a.creado_en).toLocaleDateString('es-ES')}</td>
              <td>{a.proveedor_nombre || '—'}</td><td className="num">{eur(a.base_imponible)}</td><td><Estado estado={a.estado} /></td></tr>))}
          </tbody></table>
        </section>
      )}
      {abierto && <DetalleAlbaran inicial={abierto} onCerrar={() => setAbierto(null)} onCambio={cargar} />}
      {cuadrar && <Cuadrar grupo={cuadrar} clienteId={clienteId} anio={anio} mes={mes} onCerrar={() => setCuadrar(null)} onHecho={() => { setCuadrar(null); cargar() }} />}
    </>
  )
}

function Cuadrar({ grupo, clienteId, anio, mes, onCerrar, onHecho }) {
  const revisados = grupo.filas.filter((a) => a.estado === 'revisado')
  const [sel, setSel] = useState(revisados.map((a) => a.id))
  const [cands, setCands] = useState(null)
  const [factura, setFactura] = useState(null)
  const [error, setError] = useState('')
  const suma = grupo.filas.filter((a) => sel.includes(a.id) || a.factura_compra_id === factura).reduce((s, a) => s + a.base_imponible, 0)
  useEffect(() => {
    const q = new URLSearchParams({ cliente_id: clienteId, anio, mes, suma_base: grupo.suma_base })
    if (grupo.proveedor_nif) q.set('proveedor_nif', grupo.proveedor_nif)
    else if (grupo.proveedor_nombre) q.set('proveedor_nombre', grupo.proveedor_nombre)
    api(`/api/albaranes/candidatas?${q}`).then((c) => { setCands(c); if (c[0]) setFactura(c[0].id) })
  }, [])
  const vincular = async (forzar = false) => {
    setError('')
    try {
      await api('/api/albaranes/vincular', { method: 'POST', body: { factura_id: factura, albaran_ids: sel, forzar } })
      onHecho()
    } catch (e) { setError(e.message) }
  }
  const fra = cands?.find((c) => c.id === factura)
  return (
    <Modal titulo={`Cuadrar albaranes · ${grupo.proveedor_nombre || grupo.proveedor_nif}`} onCerrar={onCerrar} ancho="720px">
      <div className="form">
        <h3>1. Factura mensual del proveedor</h3>
        {cands === null ? <p className="vacio">Buscando…</p> : cands.length === 0 ? (
          <p className="aviso">No hay ninguna factura de este proveedor entre {mes}/{anio} y los dos meses siguientes. Hay que reclamarla al proveedor (aparece en “Qué falta”).</p>
        ) : (
          <table className="tabla clicable"><tbody>
            {cands.map((c) => (
              <tr key={c.id} className={factura === c.id ? 'seleccionada' : ''} onClick={() => setFactura(c.id)}>
                <td><input type="radio" checked={factura === c.id} readOnly /></td>
                <td>{c.numero || 's/n'}</td><td>{fecha(c.fecha)}</td><td className="num">Base {eur(c.base)}</td>
                <td><Estado estado={c.estado} /></td>
                <td className={`num ${Math.abs(c.diferencia) > 0.05 ? 'negativo' : ''}`}>{Math.abs(c.diferencia) <= 0.05 ? '✓ cuadra' : `dif. ${eur(c.diferencia)}`}</td>
              </tr>))}
          </tbody></table>
        )}
        <h3>2. Albaranes revisados que incluye</h3>
        {revisados.length === 0 ? <p className="aviso">No hay albaranes revisados: revísalos antes de cuadrar.</p> : (
          <ul className="lista-check">
            {revisados.map((a) => (
              <li key={a.id}><label className="check">
                <input type="checkbox" checked={sel.includes(a.id)} onChange={(e) => setSel(e.target.checked ? [...sel, a.id] : sel.filter((x) => x !== a.id))} />
                {fecha(a.fecha)} · {a.numero || 's/n'} · {eur(a.base_imponible)}</label></li>
            ))}
          </ul>
        )}
        {fra && <p className={Math.abs(fra.base - suma) <= 0.05 ? 'ok' : 'aviso'}>Base factura {eur(fra.base)} · suma albaranes {eur(suma)} · diferencia {eur(fra.base - suma)}</p>}
        {error && <p className="error">{error}</p>}
        <div className="botonera derecha">
          {error.startsWith('No cuadra') && <button className="btn btn--peligro" onClick={() => vincular(true)}>Vincular igualmente</button>}
          <button className="btn btn--primario" disabled={!factura || !sel.length} onClick={() => vincular(false)}>Vincular</button>
        </div>
      </div>
    </Modal>
  )
}

export function DetalleAlbaran({ inicial, onCerrar, onCambio }) {
  const [a, setA] = useState(inicial)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  useEffect(() => { setA(inicial) }, [inicial])
  const set = (k) => (e) => setA({ ...a, [k]: e.target.value })
  const facturado = a.estado === 'facturado'
  const datos = () => ({ proveedor_nif: a.proveedor_nif || null, proveedor_nombre: a.proveedor_nombre || null, numero: a.numero || null,
    fecha: a.fecha || null, base_imponible: String(a.base_imponible || 0), tipo_iva: a.tipo_iva === '' || a.tipo_iva == null ? null : String(a.tipo_iva),
    total: a.total === '' || a.total == null ? null : String(a.total), notas: a.notas || null })
  const accion = async (fn, msg) => {
    setError(''); setOk('')
    try { const r = await fn(); if (r?.id) setA(r); setOk(msg); onCambio() } catch (e) { setError(e.message) }
  }
  return (
    <Cajon titulo={`Albarán ${a.numero || 's/n'}`} estado={a.estado} onCerrar={onCerrar} imagen={a.tiene_imagen ? `/api/albaranes/${a.id}/imagen` : null}>
      <div className="form rejilla">
        {a.estado === 'pendiente' && <div className="ancho"><AvisoLectura confianza={a.extraccion_confianza} avisos={a.extraccion_avisos} /></div>}
        {a.notas && <p className="nota ancho">Nota: “{a.notas}”</p>}
        {a.motivo_rechazo && <p className="error ancho">Rechazado: {a.motivo_rechazo}</p>}
        <label>NIF proveedor<input value={a.proveedor_nif || ''} onChange={set('proveedor_nif')} disabled={facturado} /></label>
        <label>Proveedor<input value={a.proveedor_nombre || ''} onChange={set('proveedor_nombre')} disabled={facturado} /></label>
        <label>Nº albarán<input value={a.numero || ''} onChange={set('numero')} disabled={facturado} /></label>
        <label>Fecha<input type="date" value={a.fecha || ''} onChange={set('fecha')} disabled={facturado} /></label>
        <label>Base imponible (€)<input type="number" step="0.01" value={a.base_imponible} onChange={set('base_imponible')} disabled={facturado} /></label>
        <label>IVA (si viene desglosado)<select value={a.tipo_iva ?? ''} onChange={set('tipo_iva')} disabled={facturado}>
          <option value="">Sin desglosar</option>{[21, 10, 5, 4, 0].map((t) => <option key={t} value={t}>{t} %</option>)}</select></label>
        {error && <p className="error ancho" role="alert">{error}</p>}
        {ok && <p className="ok ancho">{ok}</p>}
        <div className="ancho botonera">
          {!facturado && <button className="btn btn--secundario" onClick={() => accion(() => api(`/api/albaranes/${a.id}`, { method: 'PUT', body: datos() }), 'Guardado')}>Guardar</button>}
          {['pendiente', 'rechazado'].includes(a.estado) && <button className="btn btn--primario" onClick={() => accion(async () => {
            await api(`/api/albaranes/${a.id}`, { method: 'PUT', body: datos() })
            return api(`/api/albaranes/${a.id}/validar`, { method: 'POST' })
          }, 'Revisado')}>Guardar y marcar revisado</button>}
          {!facturado && a.tiene_imagen && <button className="btn btn--secundario" onClick={() => accion(() => api(`/api/albaranes/${a.id}/extraer?sobrescribir=true`, { method: 'POST' }), 'Leído de nuevo')}>Leer datos de la foto</button>}
          {facturado && <button className="btn btn--secundario" onClick={() => accion(() => api(`/api/albaranes/${a.id}/desvincular`, { method: 'POST' }), 'Quitado de la factura')}>Quitar de la factura</button>}
          {!facturado && a.estado !== 'rechazado' && <button className="btn btn--peligro" onClick={() => {
            const motivo = prompt('Motivo del rechazo (lo verá el cliente):')
            if (motivo) accion(() => api(`/api/albaranes/${a.id}/rechazar`, { method: 'POST', body: { motivo } }), 'Rechazado')
          }}>Rechazar</button>}
          {!facturado && <button className="btn btn--enlace" onClick={() => accion(async () => { await api(`/api/albaranes/${a.id}`, { method: 'DELETE' }); onCerrar() }, '')}>Borrar</button>}
        </div>
      </div>
    </Cajon>
  )
}
