// The demo token is public and documented. Change it on the Connections page for a real deployment.
const DEFAULT_TOKEN = 'pp-demo-token'

export function getToken() {
  try { return localStorage.getItem('pp_token') || DEFAULT_TOKEN } catch { return DEFAULT_TOKEN }
}
export function setToken(value) {
  try { value ? localStorage.setItem('pp_token', value) : localStorage.removeItem('pp_token') } catch { /* private mode */ }
}

async function call(path, init = {}) {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}`, ...(init.headers || {}) },
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail } catch { /* not json */ }
    if (res.status === 401) throw new Error('The API token was rejected. Set the right one on the Connections page.')
    throw new Error(typeof detail === 'string' && detail ? detail : `Request failed (${res.status}).`)
  }
  return res.json()
}

const json = (method, body) => ({ method, body: body ? JSON.stringify(body) : undefined })

export const health = () => fetch('/api/health').then((r) => (r.ok ? r.json() : Promise.reject(new Error('down'))))
export const createPost = (body) => call('/api/posts', json('POST', body))
export const listPosts = (status) => call(`/api/posts${status ? `?status=${status}` : ''}`)
export const decide = (id, body) => call(`/api/posts/${id}/decision`, json('POST', body))
export const tick = () => call('/api/scheduler/tick', json('POST'))
export const listCampaigns = () => call('/api/campaigns')
export const addCampaign = (body) => call('/api/campaigns', json('POST', body))
export const deleteCampaign = (id) => call(`/api/campaigns/${id}`, json('DELETE'))
export const runCampaign = (id) => call(`/api/campaigns/${id}/run`, json('POST'))
export const connections = () => call('/api/connections')
export const oauthStart = (provider) => call(`/api/oauth/${provider}/start`)
export const audit = () => call('/api/audit')
