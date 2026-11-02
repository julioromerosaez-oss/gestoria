import { useEffect, useMemo, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { AvisoLectura, Estado, ImagenFactura } from '../comun.jsx'

const CUENTAS_GASTO = [['600', 'Compras de mercaderías'], ['621', 'Arrendamientos'], ['622', 'Reparaciones'],
  ['623', 'Servicios profesionales'], ['624', 'Transportes'], ['625', 'Seguros'], ['626', 'Servicios bancarios'],
  ['627', 'Publicidad'], ['628', 'Suministros'], ['629', 'Otros servicios']]
const CUENTAS_INGRESO = [['700', 'Ventas de mercaderías'], ['705', 'Prestaciones de servicios']]

export default function Facturas({ tipo, clienteFijo, desde, hasta, embebido = false }) {
  const compra = tipo === 'compras'
  const ctx = useOutletContext()
  const clienteId = clienteFijo ?? ctx.clienteId
  const clientes = ctx.clientes
  const [params, setParams] = useSearchParams()
  const [facturas, setFacturas] = useState([])
  const [estado, setEstado] = useState('')
  const [abierta, setAbierta] = useState(null)

  const cargar = () => {
    const q = new URLSearchParams()
    if (clienteId) q.set('cliente_id', clienteId)
    if (estado) q.set('estado', estado)
    if (desde) q.set('desde', desde)
    if (hasta) q.set('hasta', hasta)
    return api(`/api/${tipo}?${q}`).then(setFacturas)
  }
  useEffect(() => { cargar() }, [tipo, clienteId, estado, desde, hasta])
  useEffect(() => {
    const id = params.get('abrir')
    if (id) { api(`/api/${tipo}/${id}`).then(setAbierta); const n = new URLSearchParams(params); n.delete('abrir'); setParams(n, { replace: true }) }
  }, [params])

  const nombreCliente = useMemo(() => Object.fromEntries(clientes.map((c) => [c.id, c.razon_social])), [clientes])
  const totales = facturas.filter((f) => f.estado !== 'rechazada').reduce(
    (a, f) => ({ base: a.base + f.base_imponible, iva: a.iva + f.cuota_iva, total: a.total + f.total }), { base: 0, iva: 0, total: 0 })

  return (
    <>
      <div className="cabecera">
        {embebido ? <span /> : <h1>{compra ? 'Facturas de compra' : 'Facturas de venta'}</h1>}
        <div className="acciones">
          <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
            <option value="">Todos los estados</option>
            <option value="pendiente">Pendientes de revisar</option>
            <option value="validada">Revisadas</option>
            <option value="contabilizada">Contabilizadas</option>
            <option value="rechazada">Rechazadas</option>
          </select>
          <button className="btn btn--primario" disabled={!clienteId} title={clienteId ? '' : 'Selecciona un cliente'}
            onClick={() => setAbierta({ nueva: true, cliente_id: clienteId, tipo_iva: 21, tipo_irpf: 0, base_imponible: 0,
              fecha: desde || new Date().toISOString().slice(0, 10), [compra ? 'cuenta_gasto' : 'cuenta_ingreso']: compra ? '629' : '705' })}>
            Nueva factura
          </button>
        </div>
      </div>
      <div className="resumen-linea">
        <span>{facturas.length} facturas</span><span>Base {eur(totales.base)}</span>
        <span>IVA {eur(totales.iva)}</span><span>Total {eur(totales.total)}</span>
      </div>
      <table className="tabla tarjeta clicable">
        <thead><tr>
          <th>Fecha</th><th>Número</th>{!clienteId && <th>Cliente</th>}<th>{compra ? 'Proveedor' : 'Destinatario'}</th>
          <th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th><th>Estado</th><th>Origen</th>
        </tr></thead>
        <tbody>
          {facturas.map((f) => (
            <tr key={f.id} onClick={() => setAbierta(f)}>
              <td>{fecha(f.fecha)}</td><td>{f.numero || '—'}</td>
              {!clienteId && <td>{nombreCliente[f.cliente_id]}</td>}
              <td>{(compra ? f.proveedor_nombre : f.destinatario_nombre) || '—'}</td>
              <td className="num">{eur(f.base_imponible)}</td><td className="num">{eur(f.cuota_iva)}</td>
              <td className="num">{eur(f.total)}</td>
              <td><Estado estado={f.estado} />{f.conciliada && <span className="etiqueta">Conciliada</span>}
                {f.estado === 'pendiente' && f.extraccion_confianza && <span className={`etiqueta etiqueta--${f.extraccion_confianza}`}>lectura {f.extraccion_confianza}</span>}</td>
              <td>{f.origen === 'movil' ? '📱 Móvil' : 'Gestoría'}</td>
            </tr>
          ))}
          {facturas.length === 0 && <tr><td colSpan={9} className="vacio">No hay facturas con estos filtros.</td></tr>}
        </tbody>
      </table>
      {abierta && <Detalle tipo={tipo} inicial={abierta} onCerrar={() => setAbierta(null)} onCambio={cargar} />}
    </>
  )
}

function Detalle({ tipo, inicial, onCerrar, onCambio }) {
  const compra = tipo === 'compras'
  const [f, setF] = useState(inicial)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  useEffect(() => { setF(inicial); setError(''); setOk('') }, [inicial])
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onCerrar()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCerrar])
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const bloqueada = f.estado === 'contabilizada'

  const base = Number(f.base_imponible) || 0
  const cuota = Math.round(base * (Number(f.tipo_iva) || 0)) / 100
  const ret = Math.round(base * (Number(f.tipo_irpf) || 0)) / 100

  const datos = () => {
    const comunes = { numero: f.numero || null, fecha: f.fecha || null, base_imponible: String(f.base_imponible || 0),
      tipo_iva: String(f.tipo_iva ?? 21), tipo_irpf: String(f.tipo_irpf ?? 0), concepto: f.concepto || null, notas: f.notas || null }
    return compra
      ? { ...comunes, proveedor_nif: f.proveedor_nif || null, proveedor_nombre: f.proveedor_nombre || null, cuenta_gasto: f.cuenta_gasto || '629' }
      : { ...comunes, destinatario_nif: f.destinatario_nif || null, destinatario_nombre: f.destinatario_nombre || null, cuenta_ingreso: f.cuenta_ingreso || '705' }
  }
  const accion = async (fn, mensaje) => {
    setError(''); setOk('')
    try { const r = await fn(); if (r && r.id && !r.apuntes) setF(r); setOk(mensaje); onCambio() } catch (e) { setError(e.message) }
  }
  const guardar = () => accion(async () => {
    if (f.nueva) {
      const r = await api(`/api/${tipo}`, { method: 'POST', body: { ...datos(), cliente_id: f.cliente_id } })
      return r
    }
    return api(`/api/${tipo}/${f.id}`, { method: 'PUT', body: datos() })
  }, 'Guardada')
  const guardarYValidar = () => accion(async () => {
    await api(`/api/${tipo}/${f.id}`, { method: 'PUT', body: datos() })
    return api(`/api/${tipo}/${f.id}/validar`, { method: 'POST' })
  }, 'Revisada')
  const contabilizar = () => accion(async () => {
    await api(`/api/${tipo}/${f.id}/contabilizar`, { method: 'POST' })
    return api(`/api/${tipo}/${f.id}`)
  }, 'Asiento generado')
  const rechazar = () => {
    const motivo = prompt('Motivo del rechazo (lo verá el cliente):')
    if (motivo) accion(() => api(`/api/${tipo}/${f.id}/rechazar`, { method: 'POST', body: { motivo } }), 'Rechazada')
  }
  const borrar = () => accion(async () => { await api(`/api/${tipo}/${f.id}`, { method: 'DELETE' }); onCerrar() }, '')
  const releer = () => accion(() => api(`/api/${tipo}/${f.id}/extraer?sobrescribir=true`, { method: 'POST' }), 'Datos leídos de nuevo de la foto')
  const [albaranes, setAlbaranes] = useState([])
  useEffect(() => {
    if (compra && f.id) api(`/api/albaranes?factura_id=${f.id}`).then(setAlbaranes)
  }, [f.id, f.estado])

  return (
    <div className="cajon-fondo" onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}>
      <aside className="cajon" role="dialog" aria-label="Factura">
        <header>
          <h2>{f.nueva ? 'Nueva factura' : `Factura ${f.numero || 's/n'}`}</h2>
          {!f.nueva && <Estado estado={f.estado} />}
          <button className="btn btn--icono" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </header>
        <div className={`cajon__cuerpo ${f.tiene_imagen ? 'con-imagen' : ''}`}>
          {f.tiene_imagen && <div className="cajon__imagen"><ImagenFactura ruta={`/api/${tipo}/${f.id}/imagen`} /></div>}
          <div className="form rejilla">
            {f.estado === 'pendiente' && <div className="ancho"><AvisoLectura confianza={f.extraccion_confianza} avisos={f.extraccion_avisos} /></div>}
            {f.notas && f.origen === 'movil' && <p className="nota ancho">Nota del cliente: “{f.notas}”</p>}
            {f.motivo_rechazo && <p className="error ancho">Rechazada: {f.motivo_rechazo}</p>}
            <label>Número<input value={f.numero || ''} onChange={set('numero')} disabled={bloqueada} placeholder={compra ? '' : 'Automático'} /></label>
            <label>Fecha<input type="date" value={f.fecha || ''} onChange={set('fecha')} disabled={bloqueada} /></label>
            <label>{compra ? 'NIF proveedor' : 'NIF destinatario'}<input value={(compra ? f.proveedor_nif : f.destinatario_nif) || ''} onChange={set(compra ? 'proveedor_nif' : 'destinatario_nif')} disabled={bloqueada} /></label>
            <label>{compra ? 'Proveedor' : 'Destinatario'}<input value={(compra ? f.proveedor_nombre : f.destinatario_nombre) || ''} onChange={set(compra ? 'proveedor_nombre' : 'destinatario_nombre')} disabled={bloqueada} /></label>
            <label className="ancho">Concepto<input value={f.concepto || ''} onChange={set('concepto')} disabled={bloqueada} /></label>
            <label>Base imponible (€)<input type="number" step="0.01" value={f.base_imponible} onChange={set('base_imponible')} disabled={bloqueada} /></label>
            <label>Tipo IVA<select value={Number(f.tipo_iva)} onChange={set('tipo_iva')} disabled={bloqueada}>
              {[21, 10, 5, 4, 0].map((t) => <option key={t} value={t}>{t} %</option>)}</select></label>
            <label>Retención IRPF<select value={Number(f.tipo_irpf)} onChange={set('tipo_irpf')} disabled={bloqueada}>
              {[0, 1, 2, 7, 15, 19].map((t) => <option key={t} value={t}>{t} %</option>)}</select></label>
            <label>{compra ? 'Cuenta de gasto' : 'Cuenta de ingreso'}
              <select value={compra ? f.cuenta_gasto : f.cuenta_ingreso} onChange={set(compra ? 'cuenta_gasto' : 'cuenta_ingreso')} disabled={bloqueada}>
                {(compra ? CUENTAS_GASTO : CUENTAS_INGRESO).map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
              </select></label>
            <dl className="totales ancho">
              <div><dt>Cuota IVA</dt><dd>{eur(cuota)}</dd></div>
              <div><dt>Retención</dt><dd>−{eur(ret)}</dd></div>
              <div><dt>Total</dt><dd><strong>{eur(base + cuota - ret)}</strong></dd></div>
            </dl>
            {error && <p className="error ancho" role="alert">{error}</p>}
            {ok && <p className="ok ancho">{ok}</p>}
            <div className="ancho botonera">
              {!bloqueada && <button className="btn btn--secundario" onClick={guardar}>Guardar</button>}
              {!f.nueva && ['pendiente', 'rechazada'].includes(f.estado) && <button className="btn btn--primario" onClick={guardarYValidar}>Guardar y marcar revisada</button>}
              {f.estado === 'validada' && <button className="btn btn--primario" onClick={contabilizar}>Contabilizar</button>}
              {!f.nueva && !bloqueada && f.estado !== 'rechazada' && <button className="btn btn--peligro" onClick={rechazar}>Rechazar</button>}
              {!f.nueva && !bloqueada && f.tiene_imagen && <button className="btn btn--secundario" onClick={releer} title="Vuelve a leer la foto con el OCR del servidor">Leer datos de la foto</button>}
              {!f.nueva && !bloqueada && <button className="btn btn--enlace" onClick={borrar}>Borrar</button>}
              {bloqueada && <span className="nota">Contabilizada en el asiento #{f.asiento_id}. Para corregirla, haz un asiento de rectificación.</span>}
            </div>
            {compra && albaranes.length > 0 && (
              <div className="ancho incluidos">
                <h3>Albaranes incluidos ({albaranes.length})</h3>
                <table className="tabla"><tbody>
                  {albaranes.map((a) => <tr key={a.id}><td>{fecha(a.fecha)}</td><td>{a.numero}</td><td className="num">{eur(a.base_imponible)}</td></tr>)}
                </tbody><tfoot><tr><td colSpan={2}>Suma de albaranes (base)</td>
                  <td className={`num ${Math.abs(albaranes.reduce((s, a) => s + a.base_imponible, 0) - Number(f.base_imponible)) > 0.05 ? 'negativo' : ''}`}>
                    {eur(albaranes.reduce((s, a) => s + a.base_imponible, 0))}</td></tr></tfoot></table>
              </div>
            )}
          </div>
        </div>
      </aside>
    </div>
  )
}
