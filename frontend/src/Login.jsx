import { useState } from 'react'
import { login } from './api'

export default function Login({ movil, onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault()
    setError(''); setEnviando(true)
    try { onLogin(await login(email, password)) } catch (err) { setError(err.message) } finally { setEnviando(false) }
  }

  return (
    <div className={`login ${movil ? 'login--movil' : ''}`}>
      <form className="login__caja" onSubmit={enviar}>
        <div className="marca"><img src="/icon.svg" alt="" width="36" height="36" /><span>{movil ? 'Mi Gestoría' : 'Gestoría · Panel'}</span></div>
        <h1>{movil ? 'Accede a tu área' : 'Acceso del equipo'}</h1>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Contraseña<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn--primario btn--ancho" disabled={enviando}>{enviando ? 'Entrando…' : 'Entrar'}</button>
        <p className="login__pie">Conexión cifrada · tus datos solo los ve tu gestoría</p>
      </form>
    </div>
  )
}
