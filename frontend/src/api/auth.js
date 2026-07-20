import client from './client'

// Backend login expects form-encoded fields (OAuth2 password flow).
export async function login(username, password) {
  const body = new URLSearchParams()
  body.append('username', username)
  body.append('password', password)
  const res = await client.post('/api/auth/login', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data // { access_token, token_type }
}

export async function getMe() {
  const res = await client.get('/api/auth/me')
  return res.data
}
