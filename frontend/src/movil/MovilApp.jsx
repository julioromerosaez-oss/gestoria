import { Fragment, useEffect, useRef, useState } from 'react'
import { api, eur, fecha } from '../api'
import { useSesion } from '../App.jsx'
import { Estado, ImagenFactura } from '../comun.jsx'

// Pestañas de cada rol del cliente
// La app móvil es la operativa diaria: compras y ventas. La administración usa el área web.
const NAV = {
  cliente_compras: [['subir', '＋', 'Subir'], ['docs', '☰', 'Mis subidas']],
  cliente_ventas: [['caja', '＋', 'Cierre de caja'], ['venta', '⎙', 'Factura de venta'], ['docs', '☰', 'Mis subidas']],
  cliente_compras_ventas: [['subir', '＋', 'Compras'], ['caja', '＋', 'Caja'], ['venta', '⎙', 'Venta'], ['docs', '☰', 'Mis subidas']],
}
const ROL_TXT = { cliente_compras: 'Compras', cliente_ventas: 'Ventas / caja', cliente_compras_ventas: 'Compras y ventas' }

export default function MovilApp() {
  const { usuario, salir } = useSesion()
  const nav = NAV[usuario.rol] || []
  const [pestana, setPestana] = useState(nav[0]?.[0])
  const [perfil, setPerfil] = useState(null)
  useEffect(() => { api('/api/movil/perfil').then(setPerfil) }, [])

  return (
    <div className="movil">
      <header className="movil__cab">
        <div><small>{perfil?.nombre} · {ROL_TXT[usuario.rol]}</small><strong>{perfil?.razon_social}</strong></div>
        <button className="btn btn--enlace" onClick={salir}>Salir</button>
      </header>
      <main className="movil__cuerpo">
        {pestana === 'docs' && <Documentos rol={usuario.rol} />}
        {pestana === 'subir' && <Subir key="compras" modo="compras" alTerminar={() => setPestana('docs')} />}
        {pestana === 'caja' && <CierreCaja alTerminar={() => setPestana('docs')} />}
        {pestana === 'venta' && <Subir key="ventas" modo="ventas" alTerminar={() => setPestana('docs')} />}
      </main>
      <nav className="movil__nav" style={{ gridTemplateColumns: `repeat(${nav.length}, 1fr)` }}>
        {nav.map(([id, ic, txt]) => (
          <button key={id} className={pestana === id ? 'activa' : ''} onClick={() => setPestana(id)}>
            <span className={['subir', 'caja'].includes(id) ? 'nav-subir' : ''} aria-hidden>{ic}</span>{txt}
          </button>
        ))}
      </nav>
    </div>
  )
}

/* ------------------------------------------------------------------ documentos */
const TIPO_TXT = { compra: 'Factura de gasto', venta: 'Factura de venta', albaran: 'Albarán', tpv: 'Cierre de caja' }

function Documentos({ rol }) {
  const [lista, setLista] = useState(null)
  const [filtro, setFiltro] = useState('todas')
  const [abierta, setAbierta] = useState(null)
  useEffect(() => {
    setLista(null)
    api('/api/movil/facturas').then(setLista)
  }, [])
  const filtros = {
    cliente_ventas: [['todas', 'Todo'], ['tpv', 'Caja'], ['venta', 'Facturas']],
    cliente_compras: [['todas', 'Todo'], ['compra', 'Facturas'], ['albaran', 'Albaranes']],
    cliente_compras_ventas: [['todas', 'Todo'], ['compra', 'Compras'], ['albaran', 'Albaranes'], ['tpv', 'Caja'], ['venta', 'Ventas']],
  }[rol]
  const vis = (lista || []).filter((f) => filtro === 'todas' || f.tipo === filtro)
  return (
    <>
      {filtros && <div className="m-segmento">{filtros.map(([v, t]) => <button key={v} role="radio" aria-checked={filtro === v} onClick={() => setFiltro(v)}>{t}</button>)}</div>}
      {lista === null && <p className="cargando">Cargando…</p>}
      {lista && vis.length === 0 && <p className="vacio">No hay documentos.</p>}
      <ul className="m-lista">
        {vis.map((f) => (
          <li key={`${f.tipo}${f.id}`} onClick={() => setAbierta(abierta === f ? null : f)}>
            <div className="m-lista__fila">
              <div>
                <strong>{f.tercero || (f.estado === 'pendiente' ? 'En revisión' : 'Sin nombre')}</strong>
                <small>{TIPO_TXT[f.tipo]} · {f.fecha ? fecha(f.fecha) : `subido ${new Date(f.subida).toLocaleDateString('es-ES')}`}{f.numero ? ` · nº ${f.numero}` : ''}</small>
              </div>
              <div className="derecha">
                <strong>{f.total ? eur(f.total) : '—'}</strong>
                <Estado estado={f.estado} />
              </div>
            </div>
            {['rechazada', 'rechazado'].includes(f.estado) && <p className="error">Motivo: {f.motivo_rechazo}. Vuelve a subirlo.</p>}
            {abierta === f && (
              <div className="m-detalle" onClick={(e) => e.stopPropagation()}>
                {f.total > 0 && <p>Base {eur(f.base)}{f.iva ? ` · IVA ${eur(f.iva)}` : ''}</p>}
                {f.tipo === 'albaran' && <p className="m-nota">{f.factura_id ? 'Incluido en la factura mensual del proveedor.' : 'Aún sin factura del proveedor.'}</p>}
                {f.notas && <p className="m-nota">Nota: {f.notas}</p>}
                {f.tiene_imagen && <ImagenFactura ruta={`/api/movil/facturas/${f.tipo}/${f.id}/imagen`} />}
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

/* ------------------------------------------------------------------ subir facturas y albaranes */
async function comprimir(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 600 * 1024) return file
  try {
    const bmp = await createImageBitmap(file)
    const escala = Math.min(1, 2400 / Math.max(bmp.width, bmp.height))  // suficiente para el OCR
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bmp.width * escala); canvas.height = Math.round(bmp.height * escala)
    canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.88))
    return blob && blob.size < file.size ? new File([blob], 'documento.jpg', { type: 'image/jpeg' }) : file
  } catch { return file }
}

function Captura({ archivo, setArchivo, preview, setPreview, textoBoton = 'Hacer foto' }) {
  const camara = useRef(), galeria = useRef()
  const elegir = (e) => {
    const f = e.target.files[0]
    if (!f) return
    setArchivo(f)
    setPreview(f.type.startsWith('image/') ? URL.createObjectURL(f) : null)
  }
  return (
    <>
      <input ref={camara} type="file" accept="image/*" capture="environment" hidden onChange={elegir} />
      <input ref={galeria} type="file" accept="image/*,application/pdf" hidden onChange={elegir} />
      {!archivo ? (
        <div className="m-captura">
          <button className="btn btn--primario btn--grande btn--ancho" onClick={() => camara.current.click()}>📷 {textoBoton}</button>
          <button className="btn btn--secundario btn--ancho" onClick={() => galeria.current.click()}>Elegir de la galería o PDF</button>
          <p className="m-nota">Documento entero, recto, con buena luz y sin sombras: así se lee solo.</p>
        </div>
      ) : (
        preview ? <img className="m-preview" src={preview} alt="Vista previa" /> : <div className="imagen-vacia">📄 {archivo.name}</div>
      )}
    </>
  )
}

function Leido({ r, destino }) {
  const conf = { alta: 'Leído correctamente', media: 'Leído: tu gestoría revisará los importes', baja: 'Lectura dudosa: tu gestoría completará los datos', error: 'No se ha podido leer: tu gestoría lo introducirá' }[r.confianza]
  return (
    <div className={`lectura lectura--${r.confianza}`}>
      <strong>{conf}</strong>
      <dl className="m-leido">
        <dt>Archivado como</dt><dd>{destino}</dd>
        {r.tercero && <><dt>Emisor</dt><dd>{r.tercero}{r.nif ? ` (${r.nif})` : ''}</dd></>}
        {r.numero && <><dt>Número</dt><dd>{r.numero}</dd></>}
        {r.numero_z && <><dt>Z</dt><dd>{r.numero_z}</dd></>}
        {r.fecha && <><dt>Fecha</dt><dd>{fecha(r.fecha)}</dd></>}
        {r.num_tickets != null && <><dt>Tickets</dt><dd>{r.num_tickets}</dd></>}
        {r.desglose?.map((d) => <Fragment key={d.tipo_iva}><dt>IVA {d.tipo_iva}%</dt><dd>base {eur(d.base)} · cuota {eur(d.cuota)}</dd></Fragment>)}
        {r.base != null && <><dt>Base</dt><dd>{eur(r.base)}</dd></>}
        {r.total != null && <><dt>Total</dt><dd><strong>{eur(r.total)}</strong></dd></>}
        {r.efectivo != null && (r.efectivo > 0 || r.tarjeta > 0) && <><dt>Cobros</dt><dd>efectivo {eur(r.efectivo)} · tarjeta {eur(r.tarjeta)}</dd></>}
      </dl>
      {r.avisos?.length > 0 && <ul>{r.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
    </div>
  )
}

function Subir({ modo, alTerminar }) {
  const opciones = modo === 'ventas'
    ? [['venta', 'Factura de venta']]
    : [['auto', 'Automático'], ['compra', 'Factura'], ['albaran', 'Albarán']]
  const [archivo, setArchivo] = useState(null)
  const [preview, setPreview] = useState(null)
  const [tipo, setTipo] = useState(opciones[0][0])
  const [notas, setNotas] = useState('')
  const [estado, setEstado] = useState('')
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')
  const reiniciar = () => { setArchivo(null); setPreview(null); setNotas(''); setEstado(''); setResultado(null) }
  const enviar = async () => {
    setEstado('enviando'); setError('')
    try {
      const form = new FormData()
      form.append('foto', await comprimir(archivo)); form.append('tipo', tipo)
      if (notas) form.append('notas', notas)
      setResultado(await api('/api/movil/facturas', { method: 'POST', form }))
      setEstado('ok')
    } catch (e) { setError(e.message); setEstado('') }
  }
  if (estado === 'ok') return (
    <section className="m-tarjeta m-exito">
      <div className="m-exito__icono">✓</div>
      <h2>Enviado a tu gestoría</h2>
      <Leido r={resultado.leido} destino={TIPO_TXT[resultado.tipo]} />
      <button className="btn btn--primario btn--ancho" onClick={reiniciar}>Subir otro</button>
      <button className="btn btn--enlace btn--ancho" onClick={alTerminar}>Ver mis documentos</button>
    </section>
  )
  return (
    <section className="m-tarjeta">
      <h2>{modo === 'ventas' ? 'Subir factura de venta' : 'Subir factura o albarán'}</h2>
      {opciones.length > 1 && <div className="m-segmento" role="radiogroup">
        {opciones.map(([v, t]) => <button key={v} role="radio" aria-checked={tipo === v} onClick={() => setTipo(v)}>{t}</button>)}
      </div>}
      {tipo === 'auto' && <p className="m-nota">El sistema detecta si es una factura o un albarán y lo archiva donde toca.</p>}
      <Captura archivo={archivo} setArchivo={setArchivo} preview={preview} setPreview={setPreview} />
      {archivo && (
        <>
          <label className="m-campo">Nota para tu gestoría (opcional)
            <input value={notas} onChange={(e) => setNotas(e.target.value)} placeholder="Ej.: material obra calle Mayor" maxLength={300} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn btn--primario btn--grande btn--ancho" onClick={enviar} disabled={estado === 'enviando'}>
            {estado === 'enviando' ? 'Leyendo y enviando…' : 'Enviar'}</button>
          <button className="btn btn--enlace btn--ancho" onClick={reiniciar}>Repetir foto</button>
        </>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ ventas: cierre de caja */
function CierreCaja({ alTerminar }) {
  const [archivo, setArchivo] = useState(null)
  const [preview, setPreview] = useState(null)
  const [estado, setEstado] = useState('')
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')
  const reiniciar = () => { setArchivo(null); setPreview(null); setEstado(''); setResultado(null); setError('') }
  const enviar = async () => {
    setEstado('enviando'); setError('')
    try {
      const form = new FormData()
      form.append('foto', await comprimir(archivo))
      setResultado(await api('/api/movil/cierres-z', { method: 'POST', form }))
      setEstado('ok')
    } catch (e) { setError(e.message); setEstado('') }
  }
  if (estado === 'ok') return (
    <section className="m-tarjeta m-exito">
      <div className="m-exito__icono">✓</div>
      <h2>Cierre de caja enviado</h2>
      <Leido r={resultado.leido} destino="Ventas de caja (TPV)" />
      <button className="btn btn--primario btn--ancho" onClick={reiniciar}>Subir otro cierre</button>
      <button className="btn btn--enlace btn--ancho" onClick={alTerminar}>Ver mis cierres</button>
    </section>
  )
  return (
    <section className="m-tarjeta">
      <h2>Cierre de caja del día</h2>
      <p className="m-nota">Haz una foto al ticket del informe Z del TPV al cerrar la caja. Se leen solos el desglose por IVA, el total y los cobros en efectivo y tarjeta.</p>
      <Captura archivo={archivo} setArchivo={setArchivo} preview={preview} setPreview={setPreview} textoBoton="Foto del informe Z" />
      {archivo && (
        <>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn btn--primario btn--grande btn--ancho" onClick={enviar} disabled={estado === 'enviando'}>
            {estado === 'enviando' ? 'Leyendo…' : 'Enviar cierre'}</button>
          <button className="btn btn--enlace btn--ancho" onClick={reiniciar}>Repetir foto</button>
        </>
      )}
    </section>
  )
}
