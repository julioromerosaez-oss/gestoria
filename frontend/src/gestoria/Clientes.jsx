import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import { Estado, Modal, NOMBRES_MES } from '../comun.jsx'

const VACIO = { nif: '', razon_social: '', tipo: 'autonomo', email: '', telefono: '', direccion: '', iban: '',
  regimen_iva: 'general', serie_venta: 'A', periodo_iva: 'trimestral', activo: true, notas: '' }
const soloCampos = (d) => Object.fromEntries(Object.keys(VACIO).map((k) => [k, d[k] ?? VACIO[k]]))

/** Lista de clientes: punto de entrada a todo lo demás. Pulsar un cliente abre su espacio de trabajo. */
export default function Clientes() {
  const { clientes, recargarClientes } = useOutletContext()
  const [nuevo, setNuevo] = useState(false)
  const [filtro, setFiltro] = useState('')
  const [verInactivos, setVerInactivos] = useState(false)
  const nav = useNavigate()
  const hoy = new Date()
  const mesAnterior = NOMBRES_MES[(hoy.getMonth() + 11) % 12].toLowerCase()

  const lista = clientes
    .filter((c) => verInactivos || c.activo)
    .filter((c) => `${c.razon_social} ${c.nif}`.toLowerCase().includes(filtro.toLowerCase()))
  const abrir = (c) => nav(`/clientes/${c.id}`)
  return (
    <>
      <div className="cabecera">
        <h1>Clientes</h1>
        <div className="acciones">
          <input className="buscar" autoFocus placeholder="Buscar por nombre o NIF" value={filtro} onChange={(e) => setFiltro(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && lista.length === 1 && abrir(lista[0])} />
          <label className="check"><input type="checkbox" checked={verInactivos} onChange={(e) => setVerInactivos(e.target.checked)} /> Ver inactivos</label>
          <button className="btn btn--primario" onClick={() => setNuevo(true)}>Nuevo cliente</button>
        </div>
      </div>
      <p className="ayuda">Pulsa un cliente para trabajar con él: sus facturas, albaranes, caja, IVA y cierre de cada mes.</p>
      <table className="tabla tarjeta clicable">
        <thead><tr><th>Cliente</th><th>Tipo</th><th>Por revisar</th><th>Banco sin conciliar</th><th>Cierre de {mesAnterior}</th><th /></tr></thead>
        <tbody>
          {lista.map((c) => (
            <tr key={c.id} className={c.activo ? '' : 'inactivo'} onClick={() => abrir(c)}>
              <td><strong>{c.razon_social}</strong><br /><small>{c.nif}</small></td>
              <td>{c.tipo === 'autonomo' ? 'Autónomo' : 'Sociedad'}</td>
              <td>{c.pendientes ? <span className="estado estado--pendiente">◷ {c.pendientes}</span> : <span className="ayuda-tenue">—</span>}</td>
              <td>{c.sin_conciliar ? <span className="estado estado--abierto">{c.sin_conciliar}</span> : <span className="ayuda-tenue">—</span>}</td>
              <td><Estado estado={c.estado_mes_anterior} /></td>
              <td className="derecha"><span className="flecha" aria-hidden>›</span></td>
            </tr>
          ))}
          {lista.length === 0 && <tr><td colSpan={6} className="vacio">No hay clientes que coincidan.</td></tr>}
        </tbody>
      </table>
      {nuevo && (
        <Modal titulo="Nuevo cliente" onCerrar={() => setNuevo(false)}>
          <FormCliente inicial={VACIO} onGuardado={(c) => { setNuevo(false); recargarClientes(); nav(`/clientes/${c.id}/datos`) }} />
        </Modal>
      )}
    </>
  )
}

/** Datos del cliente + usuarios de su app (sección "Datos y usuarios" del cliente). */
export function ClienteDatos() {
  const { cliente, recargarClientes } = useOutletContext()
  const [ok, setOk] = useState('')
  if (!cliente) return <p className="cargando">Cargando…</p>
  return (
    <div className="dos-columnas">
      <section className="tarjeta">
        <h2>Datos del cliente</h2>
        {ok && <p className="ok">{ok}</p>}
        <FormCliente key={cliente.id} inicial={{ ...VACIO, ...cliente }} onGuardado={() => { setOk('Guardado'); recargarClientes() }} />
      </section>
      <section className="tarjeta"><Usuarios cliente={cliente} /></section>
    </div>
  )
}

function FormCliente({ inicial, onGuardado }) {
  const [d, setD] = useState(inicial)
  const [error, setError] = useState('')
  const set = (k) => (e) => setD({ ...d, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const guardar = async (e) => {
    e.preventDefault(); setError('')
    try {
      const r = await api(d.id ? `/api/clientes/${d.id}` : '/api/clientes', { method: d.id ? 'PUT' : 'POST', body: soloCampos(d) })
      onGuardado(r)
    } catch (err) { setError(err.message) }
  }
  return (
    <form className="form rejilla" onSubmit={guardar}>
      <label>NIF / CIF<input value={d.nif} onChange={set('nif')} required /></label>
      <label>Tipo<select value={d.tipo} onChange={set('tipo')}><option value="autonomo">Autónomo</option><option value="sociedad">Sociedad</option></select></label>
      <label className="ancho">Razón social<input value={d.razon_social} onChange={set('razon_social')} required /></label>
      <label>Email<input type="email" value={d.email || ''} onChange={set('email')} /></label>
      <label>Teléfono<input value={d.telefono || ''} onChange={set('telefono')} /></label>
      <label className="ancho">Dirección<input value={d.direccion || ''} onChange={set('direccion')} /></label>
      <label>IBAN<input value={d.iban || ''} onChange={set('iban')} /></label>
      <label>Serie de facturas de venta<input value={d.serie_venta} onChange={set('serie_venta')} /></label>
      <label>Liquidación de IVA<select value={d.periodo_iva} onChange={set('periodo_iva')}>
        <option value="trimestral">Trimestral</option><option value="mensual">Mensual (gran empresa / REDEME)</option></select></label>
      <label className="check"><input type="checkbox" checked={d.activo} onChange={set('activo')} /> Cliente activo</label>
      <label className="ancho">Notas<textarea value={d.notas || ''} onChange={set('notas')} /></label>
      {error && <p className="error ancho">{error}</p>}
      <div className="ancho derecha"><button className="btn btn--primario">{d.id ? 'Guardar cambios' : 'Crear cliente'}</button></div>
    </form>
  )
}

const ROLES = [['cliente_admin', 'Administración', 've su mes, lo que falta y hace el cierre mensual'],
  ['cliente_compras', 'Compras', 'sube albaranes y facturas de proveedor'],
  ['cliente_ventas', 'Ventas / caja', 'sube los cierres Z del TPV'],
  ['cliente_compras_ventas', 'Compras y ventas', 'sube albaranes, facturas y cierres Z desde el móvil']]

function Usuarios({ cliente }) {
  const [d, setD] = useState({ nombre: '', email: '', password: '', rol: 'cliente_admin' })
  const [usuarios, setUsuarios] = useState([])
  const [mostrar, setMostrar] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const cargar = () => api(`/api/clientes/${cliente.id}/usuarios`).then(setUsuarios)
  useEffect(() => { cargar() }, [cliente.id])
  const crear = async (e) => {
    e.preventDefault(); setError(''); setMsg('')
    try {
      await api(`/api/clientes/${cliente.id}/usuarios`, { method: 'POST', body: d })
      setMsg(`Usuario creado. Entra en ${location.origin}/movil con ${d.email}.`)
      setD({ nombre: '', email: '', password: '', rol: d.rol }); setMostrar(false); cargar()
    } catch (err) { setError(err.message) }
  }
  return (
    <>
      <div className="m-cab-seccion"><h2>Usuarios de la app</h2>
        {!mostrar && <button className="btn btn--primario btn--peq" onClick={() => setMostrar(true)}>Añadir usuario</button>}</div>
      {msg && <p className="ok">{msg}</p>}
      {usuarios.length === 0 ? <p className="vacio">Este cliente aún no tiene usuarios.</p> : (
        <table className="tabla"><tbody>{usuarios.map((u) => (
          <tr key={u.id}><td><strong>{u.nombre}</strong><br /><small>{u.email}</small></td>
            <td><span className="etiqueta">{ROLES.find((r) => r[0] === u.rol)?.[1] || u.rol}</span></td></tr>))}
        </tbody></table>
      )}
      {mostrar && (
        <form className="form nuevo-usuario" onSubmit={crear}>
          <h3>Nuevo usuario</h3>
          <fieldset className="roles roles--columna">
            {ROLES.map(([v, t, desc]) => (
              <label key={v} className={`rol ${d.rol === v ? 'rol--sel' : ''}`}>
                <input type="radio" name="rol" checked={d.rol === v} onChange={() => setD({ ...d, rol: v })} />
                <strong>{t}</strong><small>{desc}</small>
              </label>))}
          </fieldset>
          <label>Nombre<input value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} required /></label>
          <label>Email<input type="email" value={d.email} onChange={(e) => setD({ ...d, email: e.target.value })} required /></label>
          <label>Contraseña inicial<input type="password" minLength={8} value={d.password} onChange={(e) => setD({ ...d, password: e.target.value })} required /></label>
          {error && <p className="error">{error}</p>}
          <div className="botonera"><button className="btn btn--primario">Crear usuario</button>
            <button type="button" className="btn btn--enlace" onClick={() => setMostrar(false)}>Cancelar</button></div>
        </form>
      )}
    </>
  )
}
