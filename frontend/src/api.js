// Cliente HTTP. El navegador SOLO habla con su propio dominio (/api/...):
// sin SDKs de terceros, sin CDNs, sin URLs externas. El login con Supabase lo hace el backend.
const T = 'gestoria_token'
const R = 'gestoria_refresh'

export async function login(email, password) {
  const r = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d.detail || 'Error de acceso')
  guardar(d)
  return d.usuario
}

function guardar(d) {
  sessionStorage.setItem(T, d.token)
  if (d.refresh_token) sessionStorage.setItem(R, d.refresh_token)
}

export async function logout() {
  const t = sessionStorage.getItem(T)
  sessionStorage.removeItem(T); sessionStorage.removeItem(R)
  if (t) await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${t}` } }).catch(() => {})
}

export async function usuarioActual() {
  if (!sessionStorage.getItem(T)) return null
  try { return await api('/api/auth/yo') } catch { return null }
}

let renovando = null
async function renovar() {
  const rt = sessionStorage.getItem(R)
  if (!rt) return false
  renovando ??= fetch('/api/auth/refresh', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }),
  }).then(async (r) => { if (!r.ok) return false; guardar(await r.json()); return true })
    .catch(() => false).finally(() => { renovando = null })
  return renovando
}

export async function api(ruta, { method = 'GET', body, form, blob } = {}, reintento = true) {
  const headers = {}
  const t = sessionStorage.getItem(T)
  if (t) headers.Authorization = `Bearer ${t}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const r = await fetch(ruta, { method, headers, body: payload })
  if (r.status === 401) {
    if (reintento && (await renovar())) return api(ruta, { method, body, form, blob }, false)
    sessionStorage.removeItem(T); sessionStorage.removeItem(R)
    window.dispatchEvent(new Event('sesion-caducada'))
  }
  if (!r.ok) {
    let msg = `Error ${r.status}`
    try { const d = await r.json(); msg = typeof d.detail === 'string' ? d.detail : (d.detail?.[0]?.msg || msg) } catch {}
    throw new Error(msg)
  }
  if (blob) return r.blob()
  if (r.status === 204) return null
  return r.json()
}

export const eur = (n) => (Number(n) || 0).toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })
export const fecha = (f) => (f ? new Date(f + (f.length === 10 ? 'T00:00' : '')).toLocaleDateString('es-ES') : '—')
export const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
export const trimestreActual = () => {
  const d = new Date(); return { anio: d.getFullYear(), trimestre: Math.floor(d.getMonth() / 3) + 1 }
}
