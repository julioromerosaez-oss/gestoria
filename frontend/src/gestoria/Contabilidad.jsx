import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api, eur, fecha } from '../api'
import { Modal } from '../comun.jsx'

export default function Contabilidad() {
  const { clienteId } = useOutletContext()
  const [vista, setVista] = useState('diario')
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear())
  const [asientos, setAsientos] = useState([])
  const [saldos, setSaldos] = useState([])
  const [nuevo, setNuevo] = useState(false)

  const cargar = () => {
    if (!clienteId) return
    api(`/api/contabilidad/asientos?cliente_id=${clienteId}&ejercicio=${ejercicio}`).then(setAsientos)
    api(`/api/contabilidad/sumas-saldos?cliente_id=${clienteId}&ejercicio=${ejercicio}`).then(setSaldos)
  }
  useEffect(cargar, [clienteId, ejercicio])

  if (!clienteId) return <><h1>Apuntes contables</h1><p className="vacio tarjeta">Selecciona un cliente arriba para ver su contabilidad.</p></>
  const tot = saldos.reduce((a, s) => ({ debe: a.debe + s.debe, haber: a.haber + s.haber }), { debe: 0, haber: 0 })
  return (
    <>
      <div className="cabecera">
        <h1>Apuntes contables</h1>
        <div className="acciones">
          <div className="pestanas" role="tablist">
            <button role="tab" aria-selected={vista === 'diario'} onClick={() => setVista('diario')}>Libro diario</button>
            <button role="tab" aria-selected={vista === 'saldos'} onClick={() => setVista('saldos')}>Sumas y saldos</button>
          </div>
          <select value={ejercicio} onChange={(e) => setEjercicio(Number(e.target.value))} aria-label="Ejercicio">
            {[0, 1, 2].map((i) => { const a = new Date().getFullYear() - i; return <option key={a}>{a}</option> })}
          </select>
          <button className="btn btn--primario" onClick={() => setNuevo(true)}>Asiento manual</button>
        </div>
      </div>
      {vista === 'diario' ? (
        <table className="tabla tarjeta diario">
          <thead><tr><th>Nº</th><th>Fecha</th><th>Cuenta</th><th>Descripción</th><th className="num">Debe</th><th className="num">Haber</th></tr></thead>
          {asientos.map((a) => (
            <tbody key={a.id} className="asiento">
              <tr className="asiento__cab"><td>{a.numero}</td><td>{fecha(a.fecha)}</td><td colSpan={4}>{a.concepto} <span className="etiqueta">{a.origen}</span></td></tr>
              {a.apuntes.map((p) => (
                <tr key={p.id}><td /><td /><td className="cuenta">{p.cuenta}</td><td>{p.descripcion}</td>
                  <td className="num">{p.debe ? eur(p.debe) : ''}</td><td className="num">{p.haber ? eur(p.haber) : ''}</td></tr>
              ))}
            </tbody>
          ))}
          {asientos.length === 0 && <tbody><tr><td colSpan={6} className="vacio">Sin asientos en {ejercicio}.</td></tr></tbody>}
        </table>
      ) : (
        <table className="tabla tarjeta">
          <thead><tr><th>Cuenta</th><th>Nombre</th><th className="num">Debe</th><th className="num">Haber</th><th className="num">Saldo</th></tr></thead>
          <tbody>
            {saldos.map((s) => (
              <tr key={s.cuenta}><td className="cuenta">{s.cuenta}</td><td>{s.nombre}</td><td className="num">{eur(s.debe)}</td>
                <td className="num">{eur(s.haber)}</td><td className={`num ${s.saldo < 0 ? 'negativo' : ''}`}>{eur(s.saldo)}</td></tr>
            ))}
          </tbody>
          <tfoot><tr><td colSpan={2}>Totales</td><td className="num">{eur(tot.debe)}</td><td className="num">{eur(tot.haber)}</td><td /></tr></tfoot>
        </table>
      )}
      {nuevo && <AsientoManual clienteId={clienteId} onCerrar={() => setNuevo(false)} onGuardado={() => { setNuevo(false); cargar() }} />}
    </>
  )
}

function AsientoManual({ clienteId, onCerrar, onGuardado }) {
  const [cab, setCab] = useState({ fecha: new Date().toISOString().slice(0, 10), concepto: '' })
  const [lineas, setLineas] = useState([{ cuenta: '', descripcion: '', debe: '', haber: '' }, { cuenta: '', descripcion: '', debe: '', haber: '' }])
  const [error, setError] = useState('')
  const debe = lineas.reduce((a, l) => a + (Number(l.debe) || 0), 0)
  const haber = lineas.reduce((a, l) => a + (Number(l.haber) || 0), 0)
  const cuadra = Math.abs(debe - haber) < 0.005 && debe > 0
  const setL = (i, k) => (e) => setLineas(lineas.map((l, j) => (j === i ? { ...l, [k]: e.target.value } : l)))
  const guardar = async (e) => {
    e.preventDefault()
    try {
      await api('/api/contabilidad/asientos', { method: 'POST', body: { cliente_id: clienteId, ...cab,
        apuntes: lineas.filter((l) => l.cuenta).map((l) => ({ ...l, descripcion: l.descripcion || cab.concepto, debe: String(l.debe || 0), haber: String(l.haber || 0) })) } })
      onGuardado()
    } catch (err) { setError(err.message) }
  }
  return (
    <Modal titulo="Asiento manual" onCerrar={onCerrar} ancho="760px">
      <form className="form" onSubmit={guardar}>
        <div className="rejilla">
          <label>Fecha<input type="date" value={cab.fecha} onChange={(e) => setCab({ ...cab, fecha: e.target.value })} required /></label>
          <label>Concepto<input value={cab.concepto} onChange={(e) => setCab({ ...cab, concepto: e.target.value })} required /></label>
        </div>
        <table className="tabla">
          <thead><tr><th>Cuenta</th><th>Descripción</th><th>Debe</th><th>Haber</th></tr></thead>
          <tbody>{lineas.map((l, i) => (
            <tr key={i}>
              <td><input value={l.cuenta} onChange={setL(i, 'cuenta')} size={6} /></td>
              <td><input value={l.descripcion} onChange={setL(i, 'descripcion')} /></td>
              <td><input type="number" step="0.01" value={l.debe} onChange={setL(i, 'debe')} /></td>
              <td><input type="number" step="0.01" value={l.haber} onChange={setL(i, 'haber')} /></td>
            </tr>))}
          </tbody>
          <tfoot><tr><td colSpan={2}><button type="button" className="btn btn--enlace" onClick={() => setLineas([...lineas, { cuenta: '', descripcion: '', debe: '', haber: '' }])}>+ Añadir línea</button></td>
            <td className="num">{eur(debe)}</td><td className="num">{eur(haber)}</td></tr></tfoot>
        </table>
        <p className={cuadra ? 'ok' : 'error'}>{cuadra ? 'El asiento cuadra' : `Descuadre: ${eur(debe - haber)}`}</p>
        {error && <p className="error">{error}</p>}
        <div className="derecha"><button className="btn btn--primario" disabled={!cuadra}>Guardar asiento</button></div>
      </form>
    </Modal>
  )
}
