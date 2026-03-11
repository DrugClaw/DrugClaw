export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function readCookie(name: string): string {
  if (typeof document === 'undefined') return ''
  const encodedName = `${encodeURIComponent(name)}=`
  const items = document.cookie ? document.cookie.split('; ') : []
  for (const item of items) {
    if (!item.startsWith(encodedName)) continue
    return decodeURIComponent(item.slice(encodedName.length))
  }
  return ''
}

function hasHeader(headers: Record<string, string>, key: string): boolean {
  const needle = key.toLowerCase()
  return Object.keys(headers).some((k) => k.toLowerCase() === needle)
}

export function makeHeaders(options: RequestInit = {}): HeadersInit {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  }
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  // Backend currently validates CSRF by scope (including some GET admin endpoints),
  // so attach token whenever present to avoid false 403 for authenticated browser sessions.
  const csrf = readCookie('mc_csrf')
  if (csrf && !hasHeader(headers, 'x-csrf-token')) {
    headers['x-csrf-token'] = csrf
  }
  return headers
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, { ...options, headers: makeHeaders(options), credentials: 'same-origin' })
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (!res.ok) {
    throw new ApiError(String(data.error || data.message || `HTTP ${res.status}`), res.status)
  }
  return data as T
}
