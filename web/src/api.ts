export type RemoteTemplateVersion = {
  version: number
  content: string
  publishedAt: string
  author: string
}

export type RemoteTemplate = {
  id: 'realtime' | 'digest'
  name: string
  description: string
  status: string
  updatedAt: string
  version: number
  draftRevision: number
  content: string
  versions: RemoteTemplateVersion[]
  allowedVariables: string[]
}

const tokenKey = 'aex-admin-api-token'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function savedToken(): string {
  return sessionStorage.getItem(tokenKey) ?? ''
}

export function rememberToken(token: string): void {
  sessionStorage.setItem(tokenKey, token)
}

export function forgetToken(): void {
  sessionStorage.removeItem(tokenKey)
}

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('无法连接管理服务，请检查 SSH 隧道是否仍在运行', 0)
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the status-based error when the server did not return JSON.
    }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

export function loadTemplates(token: string): Promise<RemoteTemplate[]> {
  return request('/api/admin/templates', token)
}

export function saveTemplateDraft(
  templateId: RemoteTemplate['id'],
  content: string,
  expectedRevision: number,
  token: string,
): Promise<RemoteTemplate> {
  return request(`/api/admin/templates/${templateId}/draft`, token, {
    method: 'PUT',
    body: JSON.stringify({ content, expected_revision: expectedRevision }),
  })
}

export function publishTemplate(
  templateId: RemoteTemplate['id'],
  expectedRevision: number,
  token: string,
): Promise<RemoteTemplate> {
  return request(`/api/admin/templates/${templateId}/publish`, token, {
    method: 'POST',
    body: JSON.stringify({ expected_revision: expectedRevision }),
  })
}

export function restoreTemplateVersion(
  templateId: RemoteTemplate['id'],
  version: number,
  expectedRevision: number,
  token: string,
): Promise<RemoteTemplate> {
  return request(`/api/admin/templates/${templateId}/versions/${version}/restore`, token, {
    method: 'POST',
    body: JSON.stringify({ expected_revision: expectedRevision }),
  })
}
