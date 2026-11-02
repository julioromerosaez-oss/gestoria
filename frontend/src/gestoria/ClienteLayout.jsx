import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Estado, ListaFalta, Modal, NOMBRES_MES, ResumenMes, SelectorMes } from '../comun.jsx'
import { SECCIONES, mesDeParams } from './Layout.jsx'

/** Marco de un cliente: cabecera, mes de trabajo (en la URL: ?mes=AAAA-MM) y sus secciones. */
export default function ClienteLayout() {
  const { id } = useParams()
  const clienteId = Number(id)
  const padre = useOutletContext()
  const cliente = padre.clientes.find((c) => c.id === clienteId)
  const [sp, setSp] = useSearchParams()
  const { anio, mes } = mesDeParams(sp)
  const loc = useLocation()
  const [estados, setEstados] = useState(null)
  const [liquidar, setLiquidar] = useState(false)
  const [version, setVersion] = useState(0)   // fuerza recarga de la sección tras liquidar/reabrir

  const refrescarEstados = () => api(`/api/clientes/${clienteId}/meses?anio=${anio}`).then(setEstados)
  useEffect(() => { refrescarEstados() }, [clienteId, anio])
  const setMes = (a, m) => {
    const n = new URLSearchParams(sp)
    n.set('mes', `${a}-${String(m).padStart(2, '0')}`)
    setSp(n)
  }
  const seccion = loc.pathname.split('/')[3] || ''
  const titulo = SECCIONES.find(([r]) => r === seccion)?.[1]
  const sinMes = ['datos'].includes(seccion)
  const estadoMes = estados?.find((e) => e.mes === mes)?.estado

  const reabrir = async () => {
    if (!confirm(`¿Reabrir ${NOMBRES_MES[mes - 1]} ${anio}? El cliente podrá volver a subir documentos de ese mes.`)) return
    await api(`/api/clientes/${clienteId}/meses/${anio}/${mes}/reabrir`, { method: 'POST' })
    refrescarEstados(); setVersion((v) => v + 1)
  }

  return (
    <>
      <div className="cab-cliente">
        <nav className="migas" aria-label="Ruta"><Link to="/clientes">Clientes</Link> <span aria-hidden>›</span> {cliente?.razon_social || '…'}</nav>
        <div className="cab-cliente__fila">
          <div>
            <h1>{titulo}</h1>
            <p className="ayuda">{cliente?.razon_social} · {cliente?.nif} · {cliente?.tipo === 'sociedad' ? 'Sociedad' : 'Autónomo'} · IVA {cliente?.periodo_iva || 'trimestral'}</p>
          </div>
          <CambiarCliente clientes={padre.clientes} actual={clienteId} />
        </div>
        {!sinMes && (
          <div className="cab-cliente__mes">
            <SelectorMes anio={anio} mes={mes} onCambio={setMes} estados={estados} />
            <span className="espacio" />
            {estadoMes && <Estado estado={estadoMes} />}
            {estadoMes && estadoMes !== 'liquidado' && <button className="btn btn--primario" onClick={() => setLiquidar(true)}>Liquidar {NOMBRES_MES[mes - 1].toLowerCase()}</button>}
            {estadoMes && estadoMes !== 'abierto' && <button className="btn btn--secundario" onClick={reabrir}>Reabrir mes</button>}
          </div>
        )}
      </div>
      <Outlet key={`${clienteId}-${version}`} context={{ ...padre, clienteId, cliente, anio, mes, setMes, refrescarEstados, setClienteId: () => {} }} />
      {liquidar && <Liquidar clienteId={clienteId} anio={anio} mes={mes} onCerrar={() => setLiquidar(false)}
        onHecho={() => { refrescarEstados(); setVersion((v) => v + 1) }} />}
    </>
  )
}

/** Buscador para saltar a otro cliente sin volver a la lista (mantiene la sección y el mes). */
function CambiarCliente({ clientes, actual }) {
  const [abierto, setAbierto] = useState(false)
  const [q, setQ] = useState('')
  const nav = useNavigate()
  const loc = useLocation()
  const ref = useRef()
  useEffect(() => {
    const fuera = (e) => ref.current && !ref.current.contains(e.target) && setAbierto(false)
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [])
  const lista = useMemo(() => clientes.filter((c) => c.id !== actual && `${c.razon_social} ${c.nif}`.toLowerCase().includes(q.toLowerCase())), [clientes, q, actual])
  const ir = (c) => {
    const resto = loc.pathname.split('/').slice(3).join('/')
    nav(`/clientes/${c.id}${resto ? '/' + resto : ''}${loc.search}`)
    setAbierto(false); setQ('')
  }
  return (
    <div className="cambiar-cliente" ref={ref}>
      <button className="btn btn--secundario" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>Cambiar de cliente ▾</button>
      {abierto && (
        <div className="cambiar-cliente__panel">
          <input autoFocus placeholder="Buscar por nombre o NIF" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && lista[0] && ir(lista[0])} />
          <ul>
            {lista.map((c) => (
              <li key={c.id}><button onClick={() => ir(c)}><strong>{c.razon_social}</strong><small>{c.nif}{c.pendientes ? ` · ${c.pendientes} por revisar` : ''}</small></button></li>
            ))}
            {lista.length === 0 && <li className="vacio">Sin resultados</li>}
          </ul>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ Resumen y qué falta */
export function ClienteResumen() {
  const { clienteId, anio, mes } = useOutletContext()
  const [datos, setDatos] = useState(null)
  const nav = useNavigate()
  const [sp] = useSearchParams()
  useEffect(() => { setDatos(null); api(`/api/clientes/${clienteId}/meses/${anio}/${mes}`).then(setDatos) }, [clienteId, anio, mes])
  const abrir = (ref) => {
    const destino = { compras: 'compras', ventas: 'ventas', albaranes: 'albaranes', 'ventas-tpv': 'caja', proveedor: 'albaranes' }[ref.tipo]
    if (destino) nav(`/clientes/${clienteId}/${destino}?${sp}`)
  }
  if (!datos) return <p className="cargando">Cargando…</p>
  return (
    <div className="dos-columnas dos-columnas--ancha">
      <section className="tarjeta"><h2>Resumen de {datos.resumen.nombre_mes}</h2><ResumenMes r={datos.resumen} /></section>
      <section className="tarjeta">
        <h2>Qué falta</h2>
        <ListaFalta items={datos.pendientes} onAbrir={abrir} />
        {datos.pendientes.some((p) => p.titulo.includes('banco')) &&
          <p className="ayuda"><Link to={`/clientes/${clienteId}/banco?${sp}`}>Ir a conciliación bancaria →</Link></p>}
      </section>
    </div>
  )
}

/* ------------------------------------------------------------------ Liquidación */
function Liquidar({ clienteId, anio, mes, onCerrar, onHecho }) {
  const [pendientes, setPendientes] = useState(null)
  const [informe, setInforme] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api(`/api/clientes/${clienteId}/meses/${anio}/${mes}`).then((d) => setPendientes(d.pendientes)) }, [])
  const bloquean = (pendientes || []).filter((p) => p.gravedad === 'bloquea')
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
          {pendientes === null && <p className="cargando">Comprobando el mes…</p>}
          {bloquean.length > 0 && <div className="aviso"><strong>Hay documentos sin revisar:</strong><ul>{bloquean.map((b) => <li key={b.titulo}>{b.titulo}</li>)}</ul>No se contabilizarán si liquidas igualmente.</div>}
          {error && <p className="error">{error}</p>}
          <div className="botonera derecha">
            {bloquean.length > 0 && <button className="btn btn--peligro" onClick={() => lanzar(true)}>Liquidar igualmente</button>}
            <button className="btn btn--primario" disabled={pendientes === null || bloquean.length > 0} onClick={() => lanzar(false)}>Liquidar</button>
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
