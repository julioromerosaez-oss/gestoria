import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import { Modal } from '../comun.jsx'

const VACIO = { nif: '', razon_social: '', tipo: 'autonomo', email: '', telefono: '', direccion: '', iban: '',
  regimen_iva: 'general', serie_venta: 'A', periodo_iva: 'trimestral', activo: true, notas: '' }

export default function Clientes() {
  const { clientes, recargarClientes, setClienteId } = useOutletContext()
  const [editando, setEditando] = useState(null)
  const [acceso, setAcceso] = useState(null)
  const [filtro, setFiltro] = useState('')
  const nav = useNavigate()

  const lista = clientes.filter((c) => `${c.razon_social} ${c.nif}`.toLowerCase().includes(filtro.toLowerCase()))
  return (
    <>
      <div className="cabecera">
        <h1>Clientes</h1>
        <div className="acciones">
          <input className="buscar" placeholder="Buscar por nombre o NIF" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
          <button className="btn btn--primario" onClick={() => setEditando(VACIO)}>Nuevo cliente</button>
        </div>
      </div>
      <table className="tabla tarjeta">
        <thead><tr><th>Razón social</th><th>NIF</th><th>Tipo</th><th>Contacto</th><th>Pendientes</th><th /></tr></thead>
        <tbody>
          {lista.map((c) => (
            <tr key={c.id} className={c.activo ? '' : 'inactivo'}>
              <td><button className="btn btn--enlace" onClick={() => { setClienteId(c.id); nav(`/clientes/${c.id}`) }}>{c.razon_social}</button></td>
              <td>{c.nif}</td>
              <td>{c.tipo === 'autonomo' ? 'Autónomo' : 'Sociedad'}</td>
              <td>{c.email || '—'}<br /><small>{c.telefono}</small></td>
              <td>{c.pendientes ? <span className="estado estado--pendiente">{c.pendientes}</span> : '—'}</td>
              <td className="derecha">
                <button className="btn btn--primario btn--peq" onClick={() => { setClienteId(c.id); nav(`/clientes/${c.id}`) }}>Abrir ficha</button>{' '}
                <button className="btn btn--secundario btn--peq" onClick={() => setAcceso(c)}>Usuarios</button>{' '}
                <button className="btn btn--secundario btn--peq" onClick={() => setEditando({ ...VACIO, ...c })}>Editar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editando && <FormCliente inicial={editando} onCerrar={() => setEditando(null)} onGuardado={() => { setEditando(null); recargarClientes() }} />}
      {acceso && <FormAcceso cliente={acceso} onCerrar={() => setAcceso(null)} />}
    </>
  )
}

function FormCliente({ inicial, onCerrar, onGuardado }) {
  const [d, setD] = useState(inicial)
  const [error, setError] = useState('')
  const set = (k) => (e) => setD({ ...d, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const guardar = async (e) => {
    e.preventDefault()
    const { id, pendientes, creado_en, ...datos } = d
    try {
      await api(id ? `/api/clientes/${id}` : '/api/clientes', { method: id ? 'PUT' : 'POST', body: datos })
      onGuardado()
    } catch (err) { setError(err.message) }
  }
  return (
    <Modal titulo={d.id ? 'Editar cliente' : 'Nuevo cliente'} onCerrar={onCerrar}>
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
        <label className="ancho">Notas<textarea value={d.notas || ''} onChange={set('notas')} /></label>
        <label className="check"><input type="checkbox" checked={d.activo} onChange={set('activo')} /> Cliente activo</label>
        {error && <p className="error ancho">{error}</p>}
        <div className="ancho derecha"><button className="btn btn--primario">Guardar</button></div>
      </form>
    </Modal>
  )
}

const ROLES = [['cliente_admin', 'Administración', 've todo su mes, lo que falta y hace el cierre mensual'],
  ['cliente_compras', 'Compras', 'sube albaranes y facturas de proveedor'],
  ['cliente_ventas', 'Ventas / caja', 'sube los cierres Z del TPV']]

function FormAcceso({ cliente, onCerrar }) {
  const [d, setD] = useState({ nombre: '', email: '', password: '', rol: 'cliente_admin' })
  const [usuarios, setUsuarios] = useState([])
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const cargar = () => api(`/api/clientes/${cliente.id}/usuarios`).then(setUsuarios)
  useEffect(() => { cargar() }, [])
  const crear = async (e) => {
    e.preventDefault(); setError(''); setMsg('')
    try {
      await api(`/api/clientes/${cliente.id}/usuarios`, { method: 'POST', body: d })
      setMsg(`Usuario creado. Entra en ${location.origin}/movil con ${d.email}.`)
      setD({ nombre: '', email: '', password: '', rol: d.rol }); cargar()
    } catch (err) { setError(err.message) }
  }
  return (
    <Modal titulo={`Usuarios de ${cliente.razon_social}`} onCerrar={onCerrar} ancho="640px">
      {usuarios.length > 0 && (
        <table className="tabla"><tbody>{usuarios.map((u) => (
          <tr key={u.id}><td>{u.nombre}</td><td>{u.email}</td><td><span className="etiqueta">{ROLES.find((r) => r[0] === u.rol)?.[1] || u.rol}</span></td></tr>))}
        </tbody></table>
      )}
      <form className="form" onSubmit={crear}>
        <h3>Nuevo usuario</h3>
        <fieldset className="roles">
          {ROLES.map(([v, t, desc]) => (
            <label key={v} className={`rol ${d.rol === v ? 'rol--sel' : ''}`}>
              <input type="radio" name="rol" checked={d.rol === v} onChange={() => setD({ ...d, rol: v })} />
              <strong>{t}</strong><small>{desc}</small>
            </label>))}
        </fieldset>
        <div className="rejilla">
          <label>Nombre<input value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} required /></label>
          <label>Email<input type="email" value={d.email} onChange={(e) => setD({ ...d, email: e.target.value })} required /></label>
        </div>
        <label>Contraseña inicial<input type="password" minLength={8} value={d.password} onChange={(e) => setD({ ...d, password: e.target.value })} required /></label>
        {error && <p className="error">{error}</p>}
        {msg && <p className="ok">{msg}</p>}
        <button className="btn btn--primario">Crear usuario</button>
      </form>
    </Modal>
  )
}
