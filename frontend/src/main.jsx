import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { createClient } from '@supabase/supabase-js'
import './styles.css'

const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_ANON_KEY)
const apiUrl = import.meta.env.VITE_API_URL.replace(/\/+$/, '')

function Login() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function google() { setBusy(true); const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } }); if (error) setMessage(error.message); setBusy(false) }
  async function magic(e) { e.preventDefault(); setBusy(true); const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } }); setMessage(error ? error.message : 'Check your email for the magic link.'); setBusy(false) }
  return <main className="center"><section className="card login"><p className="eyebrow">CARMINE</p><h1>Find the weak points before the market does.</h1><p className="muted">A founder-controlled objection queue. Platform skeleton ready; AI attacks arrive later.</p><button onClick={google} disabled={busy}>Continue with Google</button><div className="divider">or use a magic link</div><form onSubmit={magic}><input type="email" required placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} /><button className="secondary" disabled={busy}>Email me a link</button></form>{message && <p className="notice">{message}</p>}</section></main>
}

function App() {
  const [session, setSession] = useState(null)
  useEffect(() => { supabase.auth.getSession().then(({ data }) => setSession(data.session)); const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => setSession(next)); return () => listener.subscription.unsubscribe() }, [])
  if (!session) return <Login />
  return <Dashboard session={session} />
}

function Dashboard({ session }) {
  const [startup, setStartup] = useState(null)
  const [form, setForm] = useState({ name: '', idea: '', customer: '', model: '', market: '' })
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  async function call(path, options = {}) { const token = session.access_token; const response = await fetch(`${apiUrl}${path}`, { ...options, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) } }); if (!response.ok) throw new Error(await response.text()); return response.json() }
  useEffect(() => { call('/startups').then(items => { setStartup(items[0] || null); setStatus('ready') }).catch(e => { setError(e.message); setStatus('error') }) }, [])
  async function create(e) { e.preventDefault(); setStatus('loading'); setError(''); try { const made = await call('/startups', { method: 'POST', body: JSON.stringify(form) }); setStartup(made); setStatus('ready') } catch (e) { setError(e.message); setStatus('error') } }
  async function logout() { await supabase.auth.signOut() }
  if (status === 'loading') return <main className="center"><section className="card"><h2>Waking up Carmine…</h2><p className="muted">The free backend may be asleep. This can take about a minute.</p></section></main>
  return <main className="shell"><header><div><p className="eyebrow">CARMINE</p><h1>Your objection queue</h1></div><button className="link" onClick={logout}>Sign out</button></header>{error && <p className="error">Could not reach Carmine: {error}</p>}{!startup ? <section className="card form-card"><h2>Start with your startup</h2><p className="muted">Give the skeptic a profile. No AI runs yet—this creates the platform record.</p><form onSubmit={create}>{Object.entries({ name: 'Startup name', idea: 'What are you building?', customer: 'Who is the customer?', model: 'Business model', market: 'Market / geography' }).map(([key, label]) => <label key={key}>{label}<input required value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></label>)}<button>Create startup</button></form></section> : <section><div className="startup"><div><p className="eyebrow">STARTUP</p><h2>{startup.name}</h2></div><span className="pill">Empty queue</span></div><div className="empty card"><div className="empty-icon">✦</div><h2>No objections yet</h2><p className="muted">Your queue is ready. Once attack modules are built, verified objections will appear here.</p></div></section>}</main>
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)
