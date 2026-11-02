import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { Estado, ListaFalta, Modal, NOMBRES_MES, ResumenMes, SelectorMes, rangoMes } from '../comun.jsx'
import Albaranes, { DetalleAlbaran } from './Albaranes.jsx'
import Facturas from './Facturas.jsx'
import Tpv from './Tpv.jsx'

const PESTANAS = [['resumen', 'Resumen y qué falta'], ['compras', 'Facturas de compra'], ['albaranes', 'Albaranes'],
  ['ventas', 'Facturas de venta'], ['tpv', 'Caja (TPV)']]

/** Ficha del cliente para la gestoría: todo su mes (o todos sus proveedores) en una pantalla. */
export default function FichaCliente() {
  const { id } = useParams()
  const clienteId = Number(id)
  const { clientes, setClienteId } = useOutletContext()
  const cliente = clientes.find((c) => c.id === clienteId)
  const hoy = new Date()
  const [vista, setVista] = useState('mes')
  const [p, setP] = useState({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1 })
  const [estados, setEstados] = useState(null)
  useEffect(() => { setClienteId(clienteId) }, [clienteId])
  useEffect(() => { api(`/api/clientes/${clienteId}/meses?anio=${p.anio}`).then(setEstados) }, [clienteId, p.anio])
  const refrescarEstados = () => api(`/api/clientes/${clienteId}/meses?anio=${p.anio}`).then(setEstados)

  return (
    <>
      <div className="cabecera">
        <div>
          <h1>{cliente?.razon_social || 'Cliente'}</h1>
          <p className="ayuda">{cliente?.nif} · {cliente?.tipo === 'sociedad' ? 'Sociedad' : 'Autónomo'} · IVA {cliente?.periodo_iva || 'trimestral'}</p>
        </div>
        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={vista === 'mes'} onClick={() => setVista('mes')}>Por mes</button>
          <button role="tab" aria-selected={vista === 'proveedor'} onClick={() => setVista('proveedor')}>Por proveedor</button>
        </div>
      </div>
      {vista === 'mes' ? (
        <>
          <SelectorMes anio={p.anio} mes={p.mes} onCambio={(a, m) => setP({ anio: a, mes: m })} estados={estados} />
          <VistaMes clienteId={clienteId} anio={p.anio} mes={p.mes} onEstado={refrescarEstados} />
        </>
      ) : <VistaProveedores clienteId={clienteId} anio={p.anio} onAnio={(a) => setP({ ...p, anio: a })} />}
    </>
  )
}

function VistaMes({ clienteId, anio, mes, onEstado }) {
  const [pestana, setPestana] = useState('resumen')
  const [datos, setDatos] = useState(null)
  const [liquidar, setLiquidar] = useState(false)
  const [msg, setMsg] = useState('')
  const cargar = () => api(`/api/clientes/${clienteId}/meses/${anio}/${mes}`).then(setDatos)
  useEffect(() => { setDatos(null); cargar() }, [clienteId, anio, mes, pestana])
  const { desde, hasta } = rangoMes(anio, mes)
  const reabrir = async () => {
    if (!confirm(`¿Reabrir ${NOMBRES_MES[mes - 1]} ${anio}? El cliente podrá volver a subir documentos de ese mes.`)) return
    await api(`/api/clientes/${clienteId}/meses/${anio}/${mes}/reabrir`, { method: 'POST' })
    setMsg('Mes reabierto'); cargar(); onEstado()
  }
  const abrirRef = (ref) => {
    if (ref.tipo === 'proveedor') return setPestana('albaranes')
    setPestana({ compras: 'compras', ventas: 'ventas', albaranes: 'albaranes', 'ventas-tpv': 'tpv' }[ref.tipo] || 'resumen')
  }
  const r = datos?.resumen
  return (
    <>
      <div className="barra-mes">
        {r && <Estado estado={r.estado} />}
        {r?.estado === 'cerrado' && <span className="ayuda">El cliente cerró el mes el {new Date(r.cerrado_en).toLocaleDateString('es-ES')}</span>}
        {r?.estado === 'liquidado' && <span className="ayuda">Liquidado el {new Date(r.liquidado_en).toLocaleDateString('es-ES')}</span>}
        <span className="espacio" />
        {r && r.estado !== 'liquidado' && <button className="btn btn--primario" onClick={() => setLiquidar(true)}>Liquidar {NOMBRES_MES[mes - 1].toLowerCase()}</button>}
        {r && r.estado !== 'abierto' && <button className="btn btn--secundario" onClick={reabrir}>Reabrir mes</button>}
      </div>
      {msg && <p className="ok">{msg}</p>}
      <div className="pestanas pestanas--anchas" role="tablist">
        {PESTANAS.map(([k, t]) => <button key={k} role="tab" aria-selected={pestana === k} onClick={() => setPestana(k)}>{t}</button>)}
      </div>
      {pestana === 'resumen' && (!datos ? <p className="cargando">Cargando…</p> : (
        <div className="dos-columnas dos-columnas--ancha">
          <section className="tarjeta"><h2>Resumen de {r.nombre_mes}</h2><ResumenMes r={r} /></section>
          <section className="tarjeta"><h2>Qué falta</h2><ListaFalta items={datos.pendientes} onAbrir={abrirRef} /></section>
        </div>
      ))}
      {pestana === 'compras' && <Facturas tipo="compras" clienteFijo={clienteId} desde={desde} hasta={hasta} embebido />}
      {pestana === 'ventas' && <Facturas tipo="ventas" clienteFijo={clienteId} desde={desde} hasta={hasta} embebido />}
      {pestana === 'albaranes' && <Albaranes clienteFijo={clienteId} anioFijo={anio} mesFijo={mes} embebido />}
      {pestana === 'tpv' && <Tpv clienteFijo={clienteId} anioFijo={anio} mesFijo={mes} embebido />}
      {liquidar && <Liquidar clienteId={clienteId} anio={anio} mes={mes} pendientes={datos?.pendientes || []}
        onCerrar={() => setLiquidar(false)} onHecho={() => { cargar(); onEstado() }} />}
    </>
  )
}

function Liquidar({ clienteId, anio, mes, pendientes, onCerrar, onHecho }) {
  const [informe, setInforme] = useState(null)
  const [error, setError] = useState('')
  const bloquean = pendientes.filter((p) => p.gravedad === 'bloquea')
  const lanzar = async (forzar) => {
    setError('')
    try { setInforme(await api(`/api/clientes/${clienteId}/meses/${anio}/${mes}/liquidar`, { method: 'POST', body: { forzar } })); onHecho() }
    catch (e) { setError(e.message) }
  }
  return (
    <Modal titulo={`Liquidación de ${NOMBRES_MES[mes - 1]} ${anio}`} onCerrar={onCerrar} ancho="860px">
      {!informe ? (
        <div className="form">
          <p>Se contabilizarán todas las facturas y cierres de caja <strong>revisados</strong> del mes, se congelará el informe y el mes quedará bloqueado hasta que lo reabras.</p>
          {bloquean.length > 0 && <div className="aviso"><strong>Hay documentos sin revisar:</strong><ul>{bloquean.map((b) => <li key={b.titulo}>{b.titulo}</li>)}</ul>No se contabilizarán si liquidas igualmente.</div>}
          {error && <p className="error">{error}</p>}
          <div className="botonera derecha">
            {bloquean.length > 0 && <button className="btn btn--peligro" onClick={() => lanzar(true)}>Liquidar igualmente</button>}
            <button className="btn btn--primario" disabled={bloquean.length > 0} onClick={() => lanzar(false)}>Liquidar</button>
          </div>
        </div>
      ) : (
        <div className="informe">
          <p className="ok">Mes liquidado: {informe.asientos_generados} asientos generados.</p>
          <ResumenMes r={informe} />
          {informe.pendientes_al_liquidar.length > 0 && <><h3>Quedaba pendiente al liquidar</h3><ListaFalta items={informe.pendientes_al_liquidar} /></>}
          <div className="botonera derecha"><button className="btn btn--secundario" onClick={() => window.print()}>Imprimir / PDF</button></div>
        </div>
      )}
    </Modal>
  )
}

function VistaProveedores({ clienteId, anio, onAnio }) {
  const [filas, setFilas] = useState(null)
  const [sel, setSel] = useState(null)
  useEffect(() => { api(`/api/clientes/${clienteId}/proveedores?anio=${anio}`).then(setFilas) }, [clienteId, anio])
  return (
    <>
      <div className="barra-mes">
        <select value={anio} onChange={(e) => onAnio(Number(e.target.value))} aria-label="Año">
          {[0, 1, 2].map((i) => { const a = new Date().getFullYear() - i; return <option key={a}>{a}</option> })}
        </select>
        <span className="ayuda">Facturas revisadas y albaranes de {anio} agrupados por proveedor</span>
      </div>
      <table className="tabla tarjeta clicable">
        <thead><tr><th>Proveedor</th><th className="num">Facturas</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th>
          <th className="num">Albaranes</th><th>Sin factura</th><th>Meses con factura</th><th>Por revisar</th></tr></thead>
        <tbody>
          {filas?.map((f) => (
            <tr key={f.clave} onClick={() => setSel(f)}>
              <td><strong>{f.proveedor_nombre || '—'}</strong><br /><small>{f.proveedor_nif}</small></td>
              <td className="num">{f.facturas}</td><td className="num">{eur(f.base)}</td><td className="num">{eur(f.iva)}</td><td className="num">{eur(f.total)}</td>
              <td className="num">{f.albaranes ? `${f.albaranes} · ${eur(f.albaranes_base)}` : '—'}</td>
              <td>{f.albaranes_sin_factura ? <span className="estado estado--pendiente">{f.albaranes_sin_factura} albaranes</span> : '—'}</td>
              <td><span className="mini-meses">{Array.from({ length: 12 }, (_, i) => <i key={i} className={f.meses.includes(i + 1) ? 'si' : ''} title={NOMBRES_MES[i]} />)}</span></td>
              <td>{f.pendientes ? <span className="estado estado--pendiente">{f.pendientes}</span> : '—'}</td>
            </tr>))}
          {filas?.length === 0 && <tr><td colSpan={9} className="vacio">Sin proveedores en {anio}.</td></tr>}
        </tbody>
      </table>
      {sel && <DocsProveedor clienteId={clienteId} anio={anio} prov={sel} onCerrar={() => setSel(null)} />}
    </>
  )
}

function DocsProveedor({ clienteId, anio, prov, onCerrar }) {
  const [d, setD] = useState(null)
  const [alb, setAlb] = useState(null)
  const nav = useNavigate()
  const cargar = () => api(`/api/clientes/${clienteId}/proveedores/documentos?anio=${anio}&clave=${encodeURIComponent(prov.clave)}`).then(setD)
  useEffect(() => { cargar() }, [])
  return (
    <Modal titulo={`${prov.proveedor_nombre || prov.proveedor_nif} · ${anio}`} onCerrar={onCerrar} ancho="900px">
      {!d ? <p className="cargando">Cargando…</p> : (
        <div className="dos-columnas">
          <div>
            <h3>Facturas ({d.facturas.length})</h3>
            <table className="tabla clicable"><tbody>{d.facturas.map((f) => (
              <tr key={f.id} onClick={() => nav(`/compras?abrir=${f.id}`)}><td>{fecha(f.fecha)}</td><td>{f.numero}</td><td className="num">{eur(f.total)}</td><td><Estado estado={f.estado} /></td></tr>))}
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
