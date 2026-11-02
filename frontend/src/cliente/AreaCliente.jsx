import { Fragment, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useOutletContext, useSearchParams, Outlet } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { useSesion } from '../App.jsx'
import { Cajon, Estado, GraficoMargen, ListaFalta, Modal, NOMBRES_MES, ResumenMes, SelectorMes } from '../comun.jsx'
import { Liquidacion } from '../gestoria/Iva.jsx'

/**
 * Área web (escritorio) de la administración del cliente: solo ve SU empresa.
 * Consulta su mes, lo que falta y lo que tiene que reclamar, sus documentos y proveedores,
 * y hace el cierre mensual. La subida diaria de documentos se hace desde la app móvil
 * con los usuarios de compras y ventas.
 */
const MENU = [
  ['', 'Resumen del mes'],
  ['compras', 'Facturas de compra'],
  ['albaranes', 'Albaranes'],
  ['ventas', 'Facturas de venta'],
  ['caja', 'Caja (TPV)'],
  ['proveedores', 'Proveedores'],
  ['iva', 'IVA y margen'],
]

function mesDeParams(sp) {
  const v = sp.get('mes')
  if (v && /^\d{4}-\d{2}$/.test(v)) return { anio: Number(v.slice(0, 4)), mes: Number(v.slice(5)) }
  const h = new Date()
  return { anio: h.getFullYear(), mes: h.getMonth() + 1 }
}

export default function AreaCliente() {
  return (
    <Routes>
      <Route element={<Marco />}>
        <Route index element={<Resumen />} />
        <Route path="compras" element={<ListaDocs tipo="compra" />} />
        <Route path="albaranes" element={<Albaranes />} />
        <Route path="ventas" element={<ListaDocs tipo="venta" />} />
        <Route path="caja" element={<ListaDocs tipo="tpv" />} />
        <Route path="proveedores" element={<Proveedores />} />
        <Route path="iva" element={<Iva />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function Marco() {
  const { usuario, salir } = useSesion()
  const [perfil, setPerfil] = useState(null)
  const [estados, setEstados] = useState(null)
  const [sp, setSp] = useSearchParams()
  const { anio, mes } = mesDeParams(sp)
  const loc = useLocation()
  const [version, setVersion] = useState(0)
  useEffect(() => { api('/api/movil/perfil').then(setPerfil) }, [])
  const refrescar = () => api(`/api/movil/meses?anio=${anio}`).then(setEstados)
  useEffect(() => { refrescar() }, [anio])
  const setMes = (a, m) => { const n = new URLSearchParams(sp); n.set('mes', `${a}-${String(m).padStart(2, '0')}`); setSp(n) }
  const qs = `?mes=${anio}-${String(mes).padStart(2, '0')}`
  const seccion = loc.pathname.split('/')[1] || ''
  const titulo = MENU.find(([r]) => r === seccion)?.[1]
  const estadoMes = estados?.find((e) => e.mes === mes)
  const cerrar = async () => {
    if (!confirm(`¿Cerrar ${NOMBRES_MES[mes - 1]} ${anio}?\n\nYa no se podrán subir documentos con fecha de ese mes. Si después falta algo, tendrá que incluirlo tu gestoría.`)) return
    try { await api(`/api/movil/meses/${anio}/${mes}/cerrar`, { method: 'POST' }); refrescar(); setVersion((v) => v + 1) }
    catch (e) { alert(e.message) }
  }
  return (
    <div className="app app--cliente">
      <aside className="lateral">
        <div className="marca marca--empresa">
          <span className="marca__inicial" aria-hidden>{(perfil?.razon_social || '·')[0]}</span>
          <span><strong>{perfil?.razon_social || '…'}</strong><small>{perfil?.nif}</small></span>
        </div>
        <nav>
          {MENU.map(([ruta, txt]) => <NavLink key={ruta} to={`/${ruta}${qs}`} end>{txt}</NavLink>)}
        </nav>
        <div className="lateral__pie">
          <span>{usuario.nombre}</span>
          <small className="lateral__rol">Administración</small>
          <button className="btn btn--enlace" onClick={salir}>Cerrar sesión</button>
        </div>
      </aside>
      <main className="principal">
        <div className="cab-cliente">
          <div className="cab-cliente__fila">
            <div><h1>{titulo}</h1><p className="ayuda">{perfil?.razon_social}</p></div>
          </div>
          {seccion !== 'proveedores' && (
            <div className="cab-cliente__mes">
              <SelectorMes anio={anio} mes={mes} onCambio={setMes} estados={estados} />
              <span className="espacio" />
              {estadoMes && <Estado estado={estadoMes.estado} />}
              {estadoMes?.estado === 'abierto' && !estadoMes.futuro &&
                <button className="btn btn--primario" onClick={cerrar}>Cerrar {NOMBRES_MES[mes - 1].toLowerCase()}</button>}
            </div>
          )}
        </div>
        <Outlet key={version} context={{ anio, mes, perfil }} />
      </main>
    </div>
  )
}

/* ------------------------------------------------------------------ Resumen del mes */
function Resumen() {
  const { anio, mes } = useOutletContext()
  const [datos, setDatos] = useState(null)
  const [margen, setMargen] = useState(null)
  const [sp] = useSearchParams()
  useEffect(() => { setDatos(null); api(`/api/movil/meses/${anio}/${mes}`).then(setDatos) }, [anio, mes])
  useEffect(() => { api(`/api/movil/margen?anio=${anio}`).then(setMargen) }, [anio])
  if (!datos) return <p className="cargando">Cargando…</p>
  const reclamar = datos.pendientes.filter((x) => x.quien === 'proveedor')
  const resto = datos.pendientes.filter((x) => x.quien !== 'proveedor')
  return (
    <>
      <div className="dos-columnas dos-columnas--ancha">
        <section className="tarjeta"><h2>Ingresos y gastos de {datos.resumen.nombre_mes}</h2><ResumenMes r={datos.resumen} /></section>
        <div>
          <section className="tarjeta">
            <h2>Reclamar a proveedores</h2>
            {reclamar.length ? <ListaFalta items={reclamar} paraCliente /> : <p className="ok">✓ Nada que reclamar este mes.</p>}
            {reclamar.length > 0 && <p className="ayuda"><Link to={`/albaranes?${sp}`}>Ver albaranes por proveedor →</Link></p>}
          </section>
          <section className="tarjeta">
            <h2>Qué falta para cerrar el mes</h2>
            <ListaFalta items={resto} paraCliente />
          </section>
        </div>
      </div>
      {margen && (
        <section className="tarjeta">
          <h2>Ingresos y gastos de {anio} (sin IVA)</h2>
          <GraficoMargen meses={margen.meses} />
          <p className="ayuda">Margen acumulado {eur(margen.margen)} ({margen.margen_pct.toLocaleString('es-ES')} %).</p>
        </section>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ Listas de documentos */
const TXT = {
  compra: { tercero: 'Proveedor', vacio: 'No hay facturas de compra en este mes.' },
  venta: { tercero: 'Cliente', vacio: 'No hay facturas de venta en este mes.' },
  tpv: { tercero: 'Cierre', vacio: 'No hay cierres de caja en este mes.' },
}

function ListaDocs({ tipo }) {
  const { anio, mes } = useOutletContext()
  const [docs, setDocs] = useState(null)
  const [abierto, setAbierto] = useState(null)
  const [estado, setEstado] = useState('')
  useEffect(() => {
    setDocs(null)
    api(`/api/movil/facturas?anio=${anio}&mes=${mes}`).then((d) => setDocs(d.filter((x) => x.tipo === tipo)))
  }, [anio, mes, tipo])
  const vis = (docs || []).filter((d) => !estado || d.estado === estado)
  const tot = vis.filter((d) => !d.estado.startsWith('rechaz')).reduce((a, d) => ({ base: a.base + d.base, iva: a.iva + d.iva, total: a.total + d.total }), { base: 0, iva: 0, total: 0 })
  const ordenados = [...vis].sort((a, b) => (a.fecha || '9').localeCompare(b.fecha || '9'))
  return (
    <>
      <div className="barra-mes">
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos los estados</option><option value="pendiente">En revisión por la gestoría</option>
          <option value="validada">Revisadas</option><option value="contabilizada">Contabilizadas</option><option value="rechazada">Rechazadas</option>
        </select>
        <span className="resumen-linea"><span>{vis.length} documentos</span><span>Base {eur(tot.base)}</span><span>IVA {eur(tot.iva)}</span><span>Total {eur(tot.total)}</span></span>
      </div>
      {docs === null ? <p className="cargando">Cargando…</p> : (
        <table className="tabla tarjeta clicable">
          <thead><tr><th>Fecha</th><th>{tipo === 'tpv' ? 'Z' : 'Número'}</th><th>{TXT[tipo].tercero}</th>
            {tipo === 'tpv' && <><th className="num">Efectivo</th><th className="num">Tarjeta</th></>}
            <th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th><th>Estado</th></tr></thead>
          <tbody>
            {ordenados.map((d) => (
              <tr key={d.id} onClick={() => setAbierto(d)}>
                <td>{d.fecha ? fecha(d.fecha) : <span className="ayuda-tenue">en revisión</span>}</td><td>{d.numero || '—'}</td>
                <td>{tipo === 'tpv' ? `${d.num_tickets ?? '—'} tickets` : (d.tercero || <span className="ayuda-tenue">en revisión</span>)}</td>
                {tipo === 'tpv' && <><td className="num">{eur(d.efectivo)}</td><td className="num">{eur(d.tarjeta)}</td></>}
                <td className="num">{eur(d.base)}</td><td className="num">{eur(d.iva)}</td><td className="num">{eur(d.total)}</td>
                <td><Estado estado={d.estado} /></td>
              </tr>))}
            {ordenados.length === 0 && <tr><td colSpan={tipo === 'tpv' ? 9 : 7} className="vacio">{TXT[tipo].vacio}</td></tr>}
          </tbody>
        </table>
      )}
      {abierto && <VerDocumento d={abierto} onCerrar={() => setAbierto(null)} />}
    </>
  )
}

/** Ficha de solo lectura: la gestoría es quien revisa y corrige los datos. */
function VerDocumento({ d, onCerrar }) {
  const titulo = { compra: 'Factura de compra', venta: 'Factura de venta', tpv: 'Cierre de caja', albaran: 'Albarán' }[d.tipo]
  return (
    <Cajon titulo={`${titulo} ${d.numero || ''}`} estado={d.estado} onCerrar={onCerrar}
      imagen={d.tiene_imagen ? `/api/movil/facturas/${d.tipo}/${d.id}/imagen` : null}>
      <div className="form">
        {d.estado === 'pendiente' && <p className="aviso">Tu gestoría está revisando este documento. Los datos pueden cambiar.</p>}
        {['rechazada', 'rechazado'].includes(d.estado) && <p className="error">Rechazado por la gestoría: {d.motivo_rechazo}. Hay que volver a subirlo desde la app.</p>}
        <dl className="ficha">
          <dt>Fecha</dt><dd>{fecha(d.fecha)}</dd>
          {d.tipo !== 'tpv' && <><dt>{d.tipo === 'venta' ? 'Cliente' : 'Proveedor'}</dt><dd>{d.tercero || '—'}{d.tercero_nif ? ` (${d.tercero_nif})` : ''}</dd></>}
          <dt>{d.tipo === 'tpv' ? 'Nº de Z' : 'Número'}</dt><dd>{d.numero || '—'}</dd>
          {d.tipo === 'tpv' && <><dt>Tickets</dt><dd>{d.num_tickets ?? '—'}</dd>
            {d.desglose?.map((x) => <Fragment key={x.tipo_iva}><dt>IVA {x.tipo_iva} %</dt><dd>base {eur(x.base)} · cuota {eur(x.cuota)}</dd></Fragment>)}
            <dt>Cobros</dt><dd>efectivo {eur(d.efectivo)} · tarjeta {eur(d.tarjeta)}</dd></>}
          <dt>Base imponible</dt><dd>{eur(d.base)}</dd>
          {d.tipo !== 'albaran' && <><dt>IVA</dt><dd>{eur(d.iva)}</dd></>}
          <dt>Total</dt><dd><strong>{eur(d.total)}</strong></dd>
          {d.tipo === 'albaran' && <><dt>Factura del proveedor</dt><dd>{d.factura_id ? 'Incluido en la factura mensual' : 'Aún sin factura'}</dd></>}
          {d.notas && <><dt>Nota</dt><dd>{d.notas}</dd></>}
          <dt>Subido</dt><dd>{d.subida ? new Date(d.subida).toLocaleString('es-ES') : '—'}</dd>
        </dl>
      </div>
    </Cajon>
  )
}

/* ------------------------------------------------------------------ Albaranes por proveedor */
const SITUACION = {
  sin_factura: { txt: 'Reclamar la factura al proveedor', clase: 'rechazada' },
  parcial: { txt: 'Hay albaranes sin factura', clase: 'pendiente' },
  por_cuadrar: { txt: 'Factura recibida: la gestoría la está cuadrando', clase: 'validada' },
  descuadre: { txt: 'La factura no cuadra: reclamar', clase: 'rechazada' },
  cuadra: { txt: 'Cuadra con la factura', clase: 'contabilizada' },
}

function Albaranes() {
  const { anio, mes } = useOutletContext()
  const [grupos, setGrupos] = useState(null)
  const [abierto, setAbierto] = useState(null)
  useEffect(() => { setGrupos(null); api(`/api/movil/albaranes/resumen?anio=${anio}&mes=${mes}`).then(setGrupos) }, [anio, mes])
  if (!grupos) return <p className="cargando">Cargando…</p>
  return (
    <>
      <p className="ayuda">Cada proveedor debe mandar una factura al mes que coincida con la suma de sus albaranes. Si falta o no cuadra, aparece aquí para que se la reclames.</p>
      {grupos.length === 0 && <p className="vacio tarjeta">No hay albaranes en este mes.</p>}
      {grupos.map((g) => {
        const s = SITUACION[g.situacion]
        return (
          <section key={g.clave} className="tarjeta grupo-albaranes">
            <header>
              <div><strong>{g.proveedor_nombre || 'Proveedor sin identificar'}</strong>
                <small>{g.proveedor_nif || 'sin NIF'} · {g.n_albaranes} albarán(es) · {eur(g.suma_base)}</small></div>
              <span className={`estado estado--${s.clase}`}>{s.txt}{g.situacion === 'descuadre' || (g.situacion === 'por_cuadrar' && Math.abs(g.diferencia || 0) > 0.05) ? ` (dif. ${eur(g.diferencia)})` : ''}</span>
            </header>
            <table className="tabla clicable">
              <thead><tr><th>Fecha</th><th>Nº albarán</th><th className="num">Base</th><th>Estado</th></tr></thead>
              <tbody>{g.filas.map((a) => (
                <tr key={a.id} onClick={() => setAbierto({ id: a.id, tipo: 'albaran', numero: a.numero, fecha: a.fecha, tercero: a.proveedor_nombre,
                  tercero_nif: a.proveedor_nif, base: a.base_imponible, iva: 0, total: a.total || a.base_imponible, estado: a.estado,
                  motivo_rechazo: a.motivo_rechazo, tiene_imagen: a.tiene_imagen, factura_id: a.factura_compra_id, notas: a.notas, subida: a.creado_en })}>
                  <td>{fecha(a.fecha)}</td><td>{a.numero || '—'}</td><td className="num">{eur(a.base_imponible)}</td><td><Estado estado={a.estado} /></td>
                </tr>))}
              </tbody>
            </table>
          </section>
        )
      })}
      {abierto && <VerDocumento d={abierto} onCerrar={() => setAbierto(null)} />}
    </>
  )
}

/* ------------------------------------------------------------------ Proveedores */
function Proveedores() {
  const { anio } = useOutletContext()
  const [filas, setFilas] = useState(null)
  const [sel, setSel] = useState(null)
  const [docs, setDocs] = useState(null)
  useEffect(() => { api(`/api/movil/proveedores?anio=${anio}`).then(setFilas) }, [anio])
  useEffect(() => { if (sel) { setDocs(null); api(`/api/movil/proveedores/documentos?anio=${anio}&clave=${encodeURIComponent(sel.clave)}`).then(setDocs) } }, [sel])
  return (
    <>
      <p className="ayuda">Tus proveedores en {anio}: lo facturado y los albaranes que aún no tienen factura.</p>
      <table className="tabla tarjeta clicable">
        <thead><tr><th>Proveedor</th><th className="num">Facturas</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Total</th>
          <th className="num">Albaranes</th><th>Sin factura</th><th>Meses con factura</th></tr></thead>
        <tbody>{(filas || []).map((f) => (
          <tr key={f.clave} onClick={() => setSel(f)}>
            <td><strong>{f.proveedor_nombre || '—'}</strong><br /><small>{f.proveedor_nif}</small></td>
            <td className="num">{f.facturas}</td><td className="num">{eur(f.base)}</td><td className="num">{eur(f.iva)}</td><td className="num">{eur(f.total)}</td>
            <td className="num">{f.albaranes || '—'}</td>
            <td>{f.albaranes_sin_factura ? <span className="estado estado--rechazada">Reclamar ({f.albaranes_sin_factura})</span> : '—'}</td>
            <td><span className="mini-meses">{Array.from({ length: 12 }, (_, i) => <i key={i} className={f.meses.includes(i + 1) ? 'si' : ''} title={NOMBRES_MES[i]} />)}</span></td>
          </tr>))}
          {filas?.length === 0 && <tr><td colSpan={8} className="vacio">Aún no hay proveedores este año.</td></tr>}
        </tbody>
      </table>
      {sel && (
        <Modal titulo={`${sel.proveedor_nombre || sel.proveedor_nif} · ${anio}`} onCerrar={() => setSel(null)} ancho="900px">
          {!docs ? <p className="cargando">Cargando…</p> : (
            <div className="dos-columnas">
              <div><h3>Facturas ({docs.facturas.length})</h3>
                <table className="tabla"><tbody>{docs.facturas.map((f) => <tr key={f.id}><td>{fecha(f.fecha)}</td><td>{f.numero}</td><td className="num">{eur(f.total)}</td><td><Estado estado={f.estado} /></td></tr>)}</tbody></table></div>
              <div><h3>Albaranes ({docs.albaranes.length})</h3>
                <table className="tabla"><tbody>{docs.albaranes.map((a) => <tr key={a.id}><td>{fecha(a.fecha)}</td><td>{a.numero}</td><td className="num">{eur(a.base_imponible)}</td><td><Estado estado={a.estado} /></td></tr>)}</tbody></table></div>
            </div>
          )}
        </Modal>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ IVA y margen */
function Iva() {
  const { anio, mes } = useOutletContext()
  const trimestre = Math.floor((mes - 1) / 3) + 1
  const [liq, setLiq] = useState(null)
  const [margen, setMargen] = useState(null)
  useEffect(() => { api(`/api/movil/iva?anio=${anio}&trimestre=${trimestre}`).then(setLiq) }, [anio, trimestre])
  useEffect(() => { api(`/api/movil/margen?anio=${anio}`).then(setMargen) }, [anio])
  return (
    <>
      {liq && <section className="tarjeta"><h2>IVA del {trimestre}º trimestre de {anio}</h2><Liquidacion liq={liq} /></section>}
      {margen && (
        <section className="tarjeta">
          <h2>Margen {anio}</h2>
          <div className="kpis kpis--peq">
            <div className="kpi"><span className="kpi__valor">{eur(margen.ingresos)}</span><span className="kpi__titulo">Ingresos (sin IVA)</span></div>
            <div className="kpi"><span className="kpi__valor">{eur(margen.gastos)}</span><span className="kpi__titulo">Gastos (sin IVA)</span></div>
            <div className="kpi"><span className="kpi__valor">{eur(margen.margen)}</span><span className="kpi__titulo">Margen · {margen.margen_pct.toLocaleString('es-ES')} %</span></div>
          </div>
          <GraficoMargen meses={margen.meses} />
        </section>
      )}
    </>
  )
}
