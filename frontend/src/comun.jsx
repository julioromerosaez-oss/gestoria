import { useEffect, useState } from 'react'
import { api, eur, MESES } from './api'

export const NOMBRES_MES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre',
  'Octubre', 'Noviembre', 'Diciembre']

const ESTADOS = {
  pendiente: { txt: 'Pendiente de revisar', icono: '◷' },
  validada: { txt: 'Revisada', icono: '✓' },
  revisado: { txt: 'Revisado', icono: '✓' },
  facturado: { txt: 'En factura', icono: '✓✓' },
  contabilizada: { txt: 'Contabilizada', icono: '✓✓' },
  rechazada: { txt: 'Rechazada', icono: '✕' },
  rechazado: { txt: 'Rechazado', icono: '✕' },
  abierto: { txt: 'Abierto', icono: '○' },
  cerrado: { txt: 'Cerrado por el cliente', icono: '◑' },
  liquidado: { txt: 'Liquidado', icono: '●' },
}

export function Estado({ estado }) {
  const e = ESTADOS[estado] || { txt: estado, icono: '' }
  return <span className={`estado estado--${estado}`}><span aria-hidden>{e.icono}</span> {e.txt}</span>
}

/** Imagen protegida: se descarga con el token y se muestra como blob (no hay URL pública). */
export function ImagenFactura({ ruta }) {
  const [url, setUrl] = useState(null)
  const [tipo, setTipo] = useState('')
  const [error, setError] = useState(false)
  useEffect(() => {
    let u
    setUrl(null); setError(false)
    api(ruta, { blob: true }).then((b) => { u = URL.createObjectURL(b); setTipo(b.type); setUrl(u) }).catch(() => setError(true))
    return () => u && URL.revokeObjectURL(u)
  }, [ruta])
  if (error) return <div className="imagen-vacia">No se pudo cargar el documento</div>
  if (!url) return <div className="imagen-vacia">Cargando documento…</div>
  if (tipo === 'application/pdf') return <iframe className="imagen-factura" src={url} title="Factura PDF" />
  return <a href={url} target="_blank" rel="noreferrer"><img className="imagen-factura" src={url} alt="Factura" /></a>
}

/** Ingresos vs gastos por mes: barras agrupadas, 2 series (paleta validada), tooltip y leyenda. */
export function GraficoMargen({ meses, compacto = false }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...meses.flatMap((m) => [m.ingresos, m.gastos]))
  const alto = compacto ? 120 : 180
  return (
    <figure className="viz-root grafico">
      <div className="grafico__leyenda" aria-hidden>
        <span><i style={{ background: 'var(--series-1)' }} /> Ingresos</span>
        <span><i style={{ background: 'var(--series-2)' }} /> Gastos</span>
      </div>
      <div className="grafico__area" style={{ height: alto }} role="img"
        aria-label="Ingresos y gastos por mes">
        {meses.map((m) => (
          <div key={m.mes} className="grafico__mes" onMouseEnter={() => setHover(m)} onMouseLeave={() => setHover(null)}
            onTouchStart={() => setHover(m)}>
            <div className="grafico__barras">
              <span className="barra" style={{ height: `${(m.ingresos / max) * 100}%`, background: 'var(--series-1)' }} />
              <span className="barra" style={{ height: `${(m.gastos / max) * 100}%`, background: 'var(--series-2)' }} />
            </div>
            <span className="grafico__eje">{MESES[m.mes - 1].slice(0, compacto ? 1 : 3)}</span>
          </div>
        ))}
        {hover && (
          <div className="grafico__tooltip" style={{ left: `${((hover.mes - 0.5) / 12) * 100}%` }}>
            <strong>{MESES[hover.mes - 1]}</strong>
            <span>Ingresos {eur(hover.ingresos)}</span>
            <span>Gastos {eur(hover.gastos)}</span>
            <span>Margen {eur(hover.margen)}</span>
          </div>
        )}
      </div>
    </figure>
  )
}

export function Modal({ titulo, onCerrar, children, ancho }) {
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onCerrar()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCerrar])
  return (
    <div className="modal-fondo" onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}>
      <div className="modal" style={ancho ? { width: ancho } : undefined} role="dialog" aria-label={titulo}>
        <header><h2>{titulo}</h2><button className="btn btn--icono" onClick={onCerrar} aria-label="Cerrar">✕</button></header>
        {children}
      </div>
    </div>
  )
}

/** Aviso de lectura automática (OCR local): confianza + avisos. */
export function AvisoLectura({ confianza, avisos = [] }) {
  if (!confianza) return null
  const txt = { alta: 'Datos leídos de la foto: confianza alta', media: 'Datos leídos de la foto: revisa los importes',
    baja: 'Lectura dudosa: revisa todos los campos', error: 'No se pudo leer la foto: introduce los datos a mano' }[confianza]
  return (
    <div className={`lectura lectura--${confianza}`} role="status">
      <strong>{txt}</strong>
      {avisos.length > 0 && <ul>{avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
    </div>
  )
}

/** Panel lateral (cajón) con la foto a la izquierda y el formulario a la derecha. */
export function Cajon({ titulo, estado, onCerrar, imagen, children }) {
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onCerrar()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCerrar])
  return (
    <div className="cajon-fondo" onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}>
      <aside className="cajon" role="dialog" aria-label={titulo}>
        <header>
          <h2>{titulo}</h2>
          {estado && <Estado estado={estado} />}
          <button className="btn btn--icono" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </header>
        <div className={`cajon__cuerpo ${imagen ? 'con-imagen' : ''}`}>
          {imagen && <div className="cajon__imagen"><ImagenFactura ruta={imagen} /></div>}
          <div>{children}</div>
        </div>
      </aside>
    </div>
  )
}

/** Selector de mes: ‹ Octubre 2026 › con el estado del cierre de cada mes. */
export function SelectorMes({ anio, mes, onCambio, estados }) {
  const mover = (d) => {
    let m = mes + d, a = anio
    if (m < 1) { m = 12; a-- } if (m > 12) { m = 1; a++ }
    onCambio(a, m)
  }
  return (
    <div className="selector-mes">
      <button className="btn btn--icono" onClick={() => mover(-1)} aria-label="Mes anterior">‹</button>
      <strong>{NOMBRES_MES[mes - 1]} {anio}</strong>
      <button className="btn btn--icono" onClick={() => mover(1)} aria-label="Mes siguiente">›</button>
      {estados && (
        <div className="meses-chips" role="tablist">
          {estados.map((e) => (
            <button key={e.mes} role="tab" aria-selected={e.mes === mes} disabled={e.futuro}
              className={`chip-mes chip-mes--${e.estado}`} title={`${e.nombre}: ${e.estado}`}
              onClick={() => onCambio(anio, e.mes)}>{NOMBRES_MES[e.mes - 1].slice(0, 3)}</button>
          ))}
        </div>
      )}
    </div>
  )
}

export const rangoMes = (anio, mes) => {
  const d = `${anio}-${String(mes).padStart(2, '0')}-01`
  const fin = new Date(anio, mes, 0).getDate()
  return { desde: d, hasta: `${anio}-${String(mes).padStart(2, '0')}-${fin}` }
}

/** Resumen del mes con y sin IVA (lo usan la gestoría y la administración del cliente). */
export function ResumenMes({ r }) {
  return (
    <div className="resumen-mes">
      <table className="tabla tabla--resumen">
        <thead><tr><th /><th className="num">Sin IVA</th><th className="num">IVA</th><th className="num">Con IVA</th></tr></thead>
        <tbody>
          <tr><td>Ingresos por facturas <small>({r.ingresos.facturas.n})</small></td><td className="num">{eur(r.ingresos.facturas.base)}</td><td className="num">{eur(r.ingresos.facturas.iva)}</td><td className="num">{eur(r.ingresos.facturas.total)}</td></tr>
          <tr><td>Ventas de caja (TPV) <small>({r.ingresos.tpv.n} cierres)</small></td><td className="num">{eur(r.ingresos.tpv.base)}</td><td className="num">{eur(r.ingresos.tpv.iva)}</td><td className="num">{eur(r.ingresos.tpv.total)}</td></tr>
          <tr className="subtotal"><td>Total ingresos</td><td className="num">{eur(r.ingresos.base)}</td><td className="num">{eur(r.ingresos.iva)}</td><td className="num">{eur(r.ingresos.total)}</td></tr>
          <tr className="subtotal"><td>Total gastos <small>({r.gastos.n} facturas)</small></td><td className="num">{eur(r.gastos.base)}</td><td className="num">{eur(r.gastos.iva)}</td><td className="num">{eur(r.gastos.total)}</td></tr>
        </tbody>
        <tfoot><tr><td>Resultado del mes</td><td className={`num ${r.resultado_sin_iva < 0 ? 'negativo' : ''}`}>{eur(r.resultado_sin_iva)}</td><td /><td className="num">{eur(r.resultado_con_iva)}</td></tr></tfoot>
      </table>
      <div className="resumen-mes__lado">
        <div className={`resultado resultado--${r.iva_mes.resultado > 0 ? 'ingresar' : 'compensar'}`}>
          <span>IVA de {r.nombre_mes}</span>
          <strong>{eur(Math.abs(r.iva_mes.resultado))}</strong>
          <span>{r.iva_mes.situacion}</span>
        </div>
        <p className="ayuda">
          {r.periodo_iva === 'mensual' ? 'IVA mensual: se liquida este mes.' :
            <>Acumulado {r.iva_trimestre.trimestre}º trimestre: <strong>{eur(r.iva_trimestre.resultado)}</strong> {r.iva_trimestre.situacion} · plazo {r.iva_trimestre.plazo_presentacion}</>}
        </p>
        <p className="ayuda">Albaranes del mes: {r.albaranes.n} ({eur(r.albaranes.base)}){r.albaranes.sin_factura > 0 && <> · <strong>{r.albaranes.sin_factura} sin factura</strong></>}</p>
      </div>
    </div>
  )
}

const QUIEN = { gestoria: 'Gestoría', cliente: 'Cliente', proveedor: 'Proveedor' }

/** Lista de lo que falta / hay que reclamar. */
export function ListaFalta({ items, paraCliente = false, onAbrir }) {
  if (!items.length) return <p className="ok">✓ No falta nada para cerrar el mes.</p>
  return (
    <ul className="falta">
      {items.map((p, i) => (
        <li key={i} className={`falta__item falta__item--${p.gravedad}`}>
          <span className="falta__quien">{paraCliente && p.quien === 'cliente' ? 'Tú' : QUIEN[p.quien]}</span>
          <div className="falta__texto">
            <strong>{p.titulo}</strong>
            {p.detalle && <small>{p.detalle}</small>}
          </div>
          {p.importe != null && <span className="falta__importe">{eur(p.importe)}</span>}
          {onAbrir && p.ref && <button className="btn btn--secundario btn--peq" onClick={() => onAbrir(p.ref)}>Ver</button>}
        </li>
      ))}
    </ul>
  )
}
