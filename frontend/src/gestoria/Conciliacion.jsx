import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api, eur, fecha } from '../api'

export default function Conciliacion({ embebido = true }) {
  const { clienteId } = useOutletContext()
  const [movs, setMovs] = useState([])
  const [verTodos, setVerTodos] = useState(false)
  const [sel, setSel] = useState(null)
  const [sugs, setSugs] = useState([])
  const [msg, setMsg] = useState('')

  const cargar = () => clienteId && api(`/api/banco/movimientos?cliente_id=${clienteId}${verTodos ? '' : '&conciliado=false'}`).then(setMovs)
  useEffect(() => { setSel(null); cargar() }, [clienteId, verTodos])

  const elegir = async (m) => {
    setSel(m); setSugs([])
    if (!m.conciliado) setSugs(await api(`/api/banco/movimientos/${m.id}/sugerencias`))
  }
  const conciliar = async (s) => {
    try {
      await api(`/api/banco/movimientos/${sel.id}/conciliar`, { method: 'POST', body: { tipo: s.tipo, factura_id: s.factura_id } })
      setMsg(`Conciliado con la factura ${s.numero}. Asiento de ${s.tipo === 'compra' ? 'pago' : 'cobro'} generado.`)
      setSel(null); cargar()
    } catch (e) { setMsg(e.message) }
  }
  const importar = async (e) => {
    const archivo = e.target.files[0]
    if (!archivo) return
    const form = new FormData(); form.append('cliente_id', clienteId); form.append('archivo', archivo)
    try {
      const r = await api('/api/banco/importar', { method: 'POST', form })
      setMsg(`${r.importados} movimientos importados, ${r.duplicados} duplicados ignorados${r.errores.length ? `, ${r.errores.length} líneas con error` : ''}.`)
      cargar()
    } catch (err) { setMsg(err.message) }
    e.target.value = ''
  }

  if (!clienteId) return <><h1>Conciliación bancaria</h1><p className="vacio tarjeta">Selecciona un cliente arriba para conciliar sus movimientos.</p></>
  return (
    <>
      <div className="cabecera">
        {embebido ? <span /> : <h1>Conciliación bancaria</h1>}
        <div className="acciones">
          <label className="check"><input type="checkbox" checked={verTodos} onChange={(e) => setVerTodos(e.target.checked)} /> Ver también conciliados</label>
          <label className="btn btn--primario">Importar extracto CSV<input type="file" accept=".csv,text/csv" hidden onChange={importar} /></label>
        </div>
      </div>
      <p className="ayuda">Formato CSV: columnas <code>fecha;concepto;importe</code> (pagos en negativo). Se aceptan fechas dd/mm/aaaa e importes 1.234,56.</p>
      {msg && <p className="ok">{msg}</p>}
      <div className="dos-columnas">
        <table className="tabla tarjeta clicable">
          <thead><tr><th>Fecha</th><th>Concepto</th><th className="num">Importe</th><th /></tr></thead>
          <tbody>
            {movs.map((m) => (
              <tr key={m.id} onClick={() => elegir(m)} className={sel?.id === m.id ? 'seleccionada' : ''}>
                <td>{fecha(m.fecha)}</td><td>{m.concepto}</td>
                <td className={`num ${m.importe < 0 ? 'negativo' : ''}`}>{eur(m.importe)}</td>
                <td>{m.conciliado ? <span className="estado estado--contabilizada">✓ Conciliado</span> : ''}</td>
              </tr>
            ))}
            {movs.length === 0 && <tr><td colSpan={4} className="vacio">No hay movimientos pendientes de conciliar.</td></tr>}
          </tbody>
        </table>
        <section className="tarjeta panel-lateral">
          {!sel ? <p className="vacio">Elige un movimiento para ver las facturas candidatas.</p> : (
            <>
              <h2>{sel.importe < 0 ? 'Pago' : 'Cobro'} de {eur(Math.abs(sel.importe))}</h2>
              <p className="ayuda">{fecha(sel.fecha)} · {sel.concepto}</p>
              {sel.conciliado ? <p>Conciliado con la factura #{sel.factura_compra_id || sel.factura_venta_id} (asiento #{sel.asiento_id}).</p>
                : sugs.length === 0 ? <p className="vacio">No hay facturas contabilizadas con ese importe en ±90 días. Revisa si falta subir o contabilizar la factura.</p>
                : sugs.map((s) => (
                  <div key={`${s.tipo}${s.factura_id}`} className="sugerencia">
                    <div><strong>{s.tercero || 'Sin nombre'}</strong><br /><small>Fra. {s.numero || 's/n'} · {fecha(s.fecha)} · {eur(s.total)}</small></div>
                    <span className="coincidencia" title="Coincidencia">{s.puntuacion}%</span>
                    <button className="btn btn--primario btn--peq" onClick={() => conciliar(s)}>Conciliar</button>
                  </div>
                ))}
            </>
          )}
        </section>
      </div>
    </>
  )
}
