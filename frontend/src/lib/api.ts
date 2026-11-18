import type { components } from './api-types'

/** 后端 OpenAPI 生成的契约类型(技术总纲 4.2:禁止手写重复类型) */
export type Schemas = components['schemas']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const resp = await fetch(path, {
    ...init,
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new ApiError(resp.status, (body as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }
  if (resp.status === 204) return undefined as T
  return resp.json()
}

export interface ChatDone {
  content: string
  citations: Schemas['Citation'][]
}

/** 消费讲解 SSE:delta 逐段回调,done 收尾 */
export async function streamChat(
  sessionId: number,
  content: string,
  handlers: { onDelta: (t: string) => void; onDone: (d: ChatDone) => void },
): Promise<void> {
  const resp = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!resp.ok || !resp.body) throw new ApiError(resp.status, `HTTP ${resp.status}`)

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      const parsed = JSON.parse(data)
      if (event === 'delta') handlers.onDelta(parsed.text as string)
      else if (event === 'done') handlers.onDone(parsed as ChatDone)
    }
  }
}
