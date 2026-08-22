import { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import DOMPurify from 'dompurify'
import {
  ArrowDownToLine,
  Check,
  ChevronDown,
  CircleHelp,
  Code2,
  FileText,
  History,
  Info,
  KeyRound,
  LogOut,
  MessageSquareText,
  MoreHorizontal,
  PencilLine,
  Play,
  Plus,
  RotateCcw,
  Save,
  Send,
  Settings2,
  Sparkles,
  Tag,
  WandSparkles,
  X,
} from 'lucide-react'
import {
  ApiError,
  forgetToken,
  loadTemplates,
  publishTemplate,
  rememberToken,
  restoreTemplateVersion,
  savedToken,
  saveTemplateDraft,
  type RemoteTemplate,
} from './api'
import './styles.css'

type TemplateId = 'realtime' | 'digest'

type Variable = {
  key: string
  label: string
  description: string
  example: string
}

type TemplateVersion = {
  version: number
  content: string
  publishedAt: string
  author: string
}

type Template = {
  id: TemplateId
  name: string
  description: string
  icon: typeof MessageSquareText
  status: string
  updatedAt: string
  version: number
  draftRevision: number
  content: string
  versions: TemplateVersion[]
  variables: Variable[]
}

const realtimeTemplate = `<b>{title}</b>

<b>【要点】</b>

{summary}

<a href="{original_url}">↗ 阅读原文</a>　|　<a href="{my_x_url}">𝕏 Aex0x0</a>`

const digestTemplate = `<b>{report_title} · {period_label}</b>

{overview}

<b>AI 前沿信息</b>
{frontier_items}

<b>AI 应用</b>
{application_items}

<b>关键观察</b>
{key_takeaways}

{source_links}
{my_x_link}`

const realtimeVariables: Variable[] = [
  { key: 'category_line', label: '分类', description: 'AI 前沿信息或 AI 应用', example: 'AI 前沿信息' },
  { key: 'title', label: '中文标题', description: '经过筛选和翻译的消息标题', example: 'Anthropic 发布新一代模型' },
  { key: 'summary', label: '摘要', description: '消息的简洁事实摘要', example: 'Anthropic 公布了新的模型能力与 API 更新。' },
  { key: 'original_url', label: '原文链接', description: '当前消息的原文 URL，可放入 a 标签 href', example: 'https://example.com/article' },
  { key: 'my_x_url', label: '我的 X 链接', description: 'Aex0x0 的 X 主页 URL，可放入 a 标签 href', example: 'https://x.com/axe0x0' },
  { key: 'why_it_matters', label: '重点（兼容）', description: '旧模板字段，新模板不再使用', example: '模型能力提升。' },
  { key: 'links_line', label: '链接行（兼容）', description: '旧模板字段，新模板可用独立链接变量替代', example: '↗ 阅读原文 · 𝕏 Aex0x0' },
]

const digestVariables: Variable[] = [
  { key: 'report_title', label: '报告标题', description: '日报或周报', example: 'AI 日报' },
  { key: 'period_label', label: '统计周期', description: '报告覆盖的时间范围', example: '08 月 21 日' },
  { key: 'overview', label: '总览', description: '这一周期的整体判断', example: '过去 24 小时，模型与应用生态持续推进。' },
  { key: 'frontier_items', label: 'AI 前沿信息', description: '模型、平台、研究与行业更新', example: '• 新模型能力更新\n• 重要平台发布' },
  { key: 'application_items', label: 'AI 应用', description: '工作流、Agent、工具与变现机会', example: '• 一个值得试用的工作流\n• 一个热门开源项目' },
  { key: 'key_takeaways', label: '关键观察', description: '可迁移的方法和下一步判断', example: '值得继续关注模型调用成本的变化。' },
  { key: 'source_links', label: '来源链接', description: '报告中引用的原文链接', example: '🔗 阅读原文' },
  { key: 'my_x_link', label: 'Aex0x0 X 主页', description: '你的 X 账号链接', example: '𝕏 Aex0x0' },
]

const initialTemplates: Record<TemplateId, Template> = {
  realtime: {
    id: 'realtime',
    name: '日常情报',
    description: '新消息筛选后即时推送到 Telegram',
    icon: MessageSquareText,
    status: '已发布',
    updatedAt: '刚刚',
    version: 3,
    draftRevision: 1,
    content: realtimeTemplate,
    variables: realtimeVariables,
    versions: [
      { version: 3, content: realtimeTemplate, publishedAt: '2026-08-21 15:08', author: 'Aex0x0' },
      { version: 2, content: realtimeTemplate.replace('【重点】', '为什么值得关注'), publishedAt: '2026-08-20 22:41', author: 'Aex0x0' },
      { version: 1, content: '<b>{title}</b>\n\n{summary}', publishedAt: '2026-08-19 16:33', author: '系统初始化' },
    ],
  },
  digest: {
    id: 'digest',
    name: '日报 / 周报',
    description: '日报与周报共用，按标题自动区分',
    icon: FileText,
    status: '已发布',
    updatedAt: '昨天',
    version: 2,
    draftRevision: 1,
    content: digestTemplate,
    variables: digestVariables,
    versions: [
      { version: 2, content: digestTemplate, publishedAt: '2026-08-20 23:12', author: 'Aex0x0' },
      { version: 1, content: digestTemplate.replace('关键观察', '值得关注'), publishedAt: '2026-08-19 17:05', author: '系统初始化' },
    ],
  },
}

const previewValues: Record<string, string> = {
  category_line: 'AI 前沿信息',
  title: 'Anthropic 发布新一代模型，开发者工具同步更新',
  summary: 'Anthropic 公布了新的模型能力与 API 更新，重点提升长上下文任务和工具调用表现。',
  original_url: 'https://www.anthropic.com/news',
  my_x_url: 'https://x.com/axe0x0',
  why_it_matters: '模型能力和调用方式同时变化，值得及时评估对现有工作流的影响。',
  links_line: '<a href="https://www.anthropic.com/news">🔗 阅读原文</a> · <a href="https://x.com/axe0x0">𝕏 Aex0x0</a>',
  report_title: 'AI 日报',
  period_label: '2026 年 08 月 21 日',
  overview: '过去 24 小时，模型能力、开发者平台和 Agent 工具都有新的进展。',
  frontier_items: '• 新模型在长上下文与工具调用上持续增强\n• 主流厂商更新开发者 API',
  application_items: '• 开源 Agent 工具获得社区关注\n• 多个工作流开始支持更低成本的自动化',
  key_takeaways: '模型更新正在从单点能力升级，转向完整工作流的效率提升。',
  source_links: '<a href="https://www.anthropic.com/news">🔗 阅读原文</a>',
  my_x_link: '<a href="https://x.com/axe0x0">𝕏 Aex0x0</a>',
}

function fromRemote(template: RemoteTemplate): Template {
  const base = initialTemplates[template.id]
  return {
    ...base,
    ...template,
    icon: template.id === 'realtime' ? MessageSquareText : FileText,
    variables: template.id === 'realtime' ? realtimeVariables : digestVariables,
  }
}

function formatPreview(content: string): string {
  const rendered = content.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key: string) => previewValues[key] ?? `{${key}}`)
  return DOMPurify.sanitize(rendered, {
    ALLOWED_TAGS: ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'code', 'pre', 'blockquote'],
    ALLOWED_ATTR: ['href'],
  })
}

function App() {
  const [templates, setTemplates] = useState<Record<TemplateId, Template>>(initialTemplates)
  const [activeId, setActiveId] = useState<TemplateId>('realtime')
  const [draft, setDraft] = useState(templates.realtime.content)
  const [savedDraft, setSavedDraft] = useState(templates.realtime.content)
  const [activeTab, setActiveTab] = useState<'editor' | 'history'>('editor')
  const [toast, setToast] = useState<string | null>(null)
  const [showVariableGuide, setShowVariableGuide] = useState(true)
  const [apiToken, setApiToken] = useState(savedToken)
  const [tokenInput, setTokenInput] = useState('')
  const [authState, setAuthState] = useState<'required' | 'loading' | 'ready'>('loading')
  const [authError, setAuthError] = useState('')
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const active = templates[activeId]
  const isDirty = draft !== savedDraft
  const variables = active.variables

  useEffect(() => {
    if (!apiToken) {
      setAuthState('required')
      return
    }
    void connect(apiToken)
  }, [])

  useEffect(() => {
    setDraft(active.content)
    setSavedDraft(active.content)
    setActiveTab('editor')
  }, [activeId])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2800)
    return () => window.clearTimeout(timer)
  }, [toast])

  const previewHtml = useMemo(() => formatPreview(draft), [draft])

  function selectTemplate(id: TemplateId) {
    if (id === activeId) return
    if (isDirty && !window.confirm('当前模板有未保存修改，确定切换吗？')) return
    setActiveId(id)
  }

  function updateDraft(value: string) {
    setDraft(value)
  }

  function applyRemote(template: RemoteTemplate) {
    const next = fromRemote(template)
    setTemplates((current) => ({ ...current, [template.id]: next }))
    if (template.id === activeId) {
      setDraft(template.content)
      setSavedDraft(template.content)
    }
    return next
  }

  async function connect(token: string) {
    setAuthState('loading')
    setAuthError('')
    try {
      const remote = await loadTemplates(token)
      const next = { ...initialTemplates }
      for (const template of remote) next[template.id] = fromRemote(template)
      setTemplates(next)
      setDraft(next[activeId].content)
      setSavedDraft(next[activeId].content)
      setApiToken(token)
      rememberToken(token)
      setAuthState('ready')
    } catch (error) {
      forgetToken()
      setAuthState('required')
      setAuthError(error instanceof Error ? error.message : '无法连接管理服务')
    }
  }

  async function saveDraft(): Promise<Template | null> {
    if (!apiToken || saving) return null
    setSaving(true)
    try {
      const remote = await saveTemplateDraft(activeId, draft, active.draftRevision, apiToken)
      const next = applyRemote(remote)
      setToast('草稿已保存到服务器')
      return next
    } catch (error) {
      handleApiError(error)
      return null
    } finally {
      setSaving(false)
    }
  }

  async function publish() {
    if (!apiToken || saving) return
    setSaving(true)
    try {
      let current = active
      if (isDirty) {
        const saved = await saveTemplateDraft(activeId, draft, active.draftRevision, apiToken)
        current = applyRemote(saved)
      }
      const published = await publishTemplate(activeId, current.draftRevision, apiToken)
      applyRemote(published)
      setToast(`v${published.version} 已发布，后续 Telegram 消息立即使用`)
    } catch (error) {
      handleApiError(error)
    } finally {
      setSaving(false)
    }
  }

  async function rollback(version: TemplateVersion) {
    if (!apiToken || saving) return
    setSaving(true)
    try {
      const restored = await restoreTemplateVersion(activeId, version.version, active.draftRevision, apiToken)
      applyRemote(restored)
      setToast(restored.status === '草稿' ? `已将 v${version.version} 恢复为草稿，请确认后发布` : `已恢复到当前发布版本 v${version.version}`)
      setActiveTab('editor')
    } catch (error) {
      handleApiError(error)
    } finally {
      setSaving(false)
    }
  }

  function handleApiError(error: unknown) {
    const message = error instanceof Error ? error.message : '管理服务请求失败'
    setToast(message)
    if (error instanceof ApiError && (error.status === 401 || error.status === 503)) {
      forgetToken()
      setApiToken('')
      setAuthError(message)
      setAuthState('required')
    }
  }

  function logout() {
    forgetToken()
    setApiToken('')
    setTokenInput('')
    setAuthError('')
    setAuthState('required')
  }

  function insertVariable(variable: Variable) {
    const textarea = textareaRef.current
    const token = `{${variable.key}}`
    if (!textarea) {
      setDraft((value) => `${value}${value.endsWith('\n') ? '' : '\n'}${token}`)
      return
    }
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const next = `${draft.slice(0, start)}${token}${draft.slice(end)}`
    setDraft(next)
    requestAnimationFrame(() => {
      textarea.focus()
      const position = start + token.length
      textarea.setSelectionRange(position, position)
    })
  }

  function testSend() {
    setToast(activeId === 'realtime' ? '已生成一条日常模板测试预览' : '已生成一条日报模板测试预览')
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><Sparkles size={17} /></div>
          <div><div className="brand-name">Aex AI 情报</div><div className="brand-subtitle">管理中枢</div></div>
        </div>
        <div className="topbar-center"><span className="workspace-dot" />个人工作区 <ChevronDown size={14} /></div>
        <div className="topbar-actions">
          <button className="icon-button" title="帮助"><CircleHelp size={18} /></button>
          {authState === 'ready' && <button className="icon-button" title="退出管理会话" onClick={logout}><LogOut size={17} /></button>}
          <button className="avatar" title="当前用户">A</button>
        </div>
      </header>

      <main className="page-shell">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><Settings2 size={14} />配置中心</div>
            <h1>模板管理</h1>
            <p>管理 Telegram 的消息格式，保存草稿后再发布到 Worker。</p>
          </div>
          <div className="heading-actions">
            <div className={`save-state ${isDirty ? 'unsaved' : ''}`}><span className="state-dot" />{isDirty ? '有未保存修改' : '已保存'}</div>
            <button className="button secondary" onClick={saveDraft} disabled={!isDirty || saving || authState !== 'ready'}><Save size={16} />{saving ? '处理中' : '保存草稿'}</button>
            <button className="button primary" onClick={publish} disabled={saving || authState !== 'ready' || (!isDirty && active.status === '已发布')}><Send size={16} />发布版本</button>
          </div>
        </div>

        <div className="content-grid">
          <aside className="sidebar panel">
            <div className="panel-heading"><div><span className="section-kicker">WORKSPACE</span><h2>消息模板</h2></div><button className="icon-button subtle" title="更多操作"><MoreHorizontal size={18} /></button></div>
            <div className="template-list">
              {(Object.values(templates) as Template[]).map((template) => {
                const Icon = template.icon
                const selected = activeId === template.id
                return <button key={template.id} className={`template-item ${selected ? 'selected' : ''}`} onClick={() => selectTemplate(template.id)}>
                  <span className={`template-icon ${template.id}`}><Icon size={17} /></span>
                  <span className="template-item-copy"><strong>{template.name}</strong><small>{template.description}</small><span className="item-meta"><span className={`status-pill ${template.status === '草稿' ? 'draft' : ''}`}>{template.status}</span><span>v{template.version}</span></span></span>
                  {selected && <span className="selected-line" />}
                </button>
              })}
            </div>
            <div className="sidebar-note"><Info size={15} /><span>日报与周报共用同一套模板，通过 <code>report_title</code> 区分。</span></div>
            <div className="sidebar-footer"><div className="sync-row"><span className="sync-icon"><Check size={13} /></span><span>已连接管理 API</span><span className="sync-time">在线</span></div><div className="powered">Aex AI 情报系统 · v0.2</div></div>
          </aside>

          <section className="editor-column panel">
            <div className="editor-header">
              <div className="editor-title"><span className={`large-template-icon ${activeId}`} >{activeId === 'realtime' ? <MessageSquareText size={20} /> : <FileText size={20} />}</span><div><h2>{active.name}</h2><div className="editor-meta"><span className="status-pill">{active.status}</span><span>最后修改 {active.updatedAt}</span><span className="version-label">v{active.version}</span></div></div></div>
              <div className="editor-tools"><button className="icon-button subtle" title="恢复当前已保存内容" onClick={() => setDraft(savedDraft)}><RotateCcw size={17} /></button><button className="button ghost" onClick={() => setActiveTab('history')}><History size={16} />版本历史</button></div>
            </div>
            <div className="tab-bar"><button className={activeTab === 'editor' ? 'active' : ''} onClick={() => setActiveTab('editor')}><Code2 size={15} />编辑模板</button><button className={activeTab === 'history' ? 'active' : ''} onClick={() => setActiveTab('history')}><History size={15} />历史版本 <span className="tab-count">{active.versions.length}</span></button></div>
            {activeTab === 'editor' ? <>
              <div className="editor-toolbar"><div className="format-hint"><span className="toolbar-token">HTML</span><span>Telegram HTML 格式</span></div><button className="button tiny" onClick={() => setDraft((value) => value.replaceAll('【AI 前沿信息】', '【AI 前沿信息】'))}><WandSparkles size={14} />格式检查</button></div>
              <div className="editor-wrap"><textarea ref={textareaRef} value={draft} onChange={(event) => updateDraft(event.target.value)} spellCheck={false} aria-label="模板编辑器" /><div className="line-count">{draft.split('\n').length} 行 · {draft.length} 字符</div></div>
              <div className="preview-header"><div><span className="section-kicker">LIVE PREVIEW</span><h3>Telegram 预览</h3></div><button className="button tiny" onClick={testSend}><Play size={14} />测试预览</button></div>
              <div className="telegram-preview"><div className="telegram-top"><span className="telegram-avatar">A</span><div><strong>Aex AI 前沿</strong><small>频道 · 刚刚</small></div><MoreHorizontal size={17} /></div><div className="telegram-body" dangerouslySetInnerHTML={{ __html: previewHtml }} /><div className="telegram-footer"><span>刚刚</span><span>✓✓</span></div></div>
            </> : <div className="history-list">{active.versions.map((version, index) => <div className={`history-item ${index === 0 ? 'current' : ''}`} key={`${version.version}-${version.publishedAt}`}><div className="history-version"><span className="version-badge">v{version.version}</span>{index === 0 && <span className="current-badge">当前发布</span>}<span className="history-date">{version.publishedAt}</span></div><div className="history-content"><code>{version.content.slice(0, 130).replaceAll('\n', ' ')}{version.content.length > 130 ? '…' : ''}</code><button className="button tiny" onClick={() => rollback(version)}><ArrowDownToLine size={14} />载入此版本</button></div><div className="history-author">由 {version.author} 发布</div></div>)}</div>}
          </section>

          <aside className="right-column">
            <section className="panel variables-panel"><div className="panel-heading"><div><span className="section-kicker">REFERENCE</span><h2>可用变量</h2></div><button className="icon-button subtle" title="变量帮助"><CircleHelp size={17} /></button></div><p className="panel-description">点击变量即可插入到光标位置。变量由 Worker 在发送前替换。</p><div className="variable-list">{variables.map((variable) => <button className="variable-item" key={variable.key} onClick={() => insertVariable(variable)}><span className="variable-icon"><Tag size={14} /></span><span className="variable-copy"><code>{`{${variable.key}}`}</code><strong>{variable.label}</strong><small>{variable.description}</small></span><Plus size={15} /></button>)}</div><button className="guide-toggle" onClick={() => setShowVariableGuide((value) => !value)}><Info size={14} />{showVariableGuide ? '收起使用说明' : '查看使用说明'}</button>{showVariableGuide && <div className="variable-guide"><strong>模板小提示</strong><span>保留变量名称的花括号，发送时才会被真实内容替换。</span><span>Telegram 支持 <code>&lt;b&gt;</code> 粗体和 <code>&lt;a href&gt;</code> 链接。</span></div>}</section>
            <section className="panel quick-panel"><div className="panel-heading"><div><span className="section-kicker">QUICK ACTIONS</span><h2>快捷操作</h2></div></div><button className="quick-action" onClick={() => setDraft(active.id === 'realtime' ? realtimeTemplate : digestTemplate)}><PencilLine size={16} /><span><strong>恢复系统模板</strong><small>撤销当前编辑内容</small></span><ChevronDown size={15} /></button><button className="quick-action" onClick={testSend}><Send size={16} /><span><strong>发送测试预览</strong><small>只生成预览，不发送到频道</small></span><ChevronDown size={15} /></button></section>
          </aside>
        </div>
      </main>
      {authState !== 'ready' && <div className="auth-overlay">
        <form className="auth-dialog" onSubmit={(event) => { event.preventDefault(); if (tokenInput.trim()) void connect(tokenInput.trim()) }}>
          <span className="auth-icon"><KeyRound size={20} /></span>
          <span className="section-kicker">PRIVATE ADMIN</span>
          <h2>连接模板管理服务</h2>
          <p>输入服务器 <code>ADMIN_API_TOKEN</code>。凭据只保存在当前浏览器会话中，关闭标签后自动清除。</p>
          <label htmlFor="admin-token">管理 Token</label>
          <input id="admin-token" type="password" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="输入管理 Token" autoComplete="current-password" autoFocus />
          {authError && <div className="auth-error">{authError}</div>}
          <button className="button primary auth-submit" type="submit" disabled={!tokenInput.trim() || authState === 'loading'}>{authState === 'loading' ? '正在连接…' : '进入管理中枢'}</button>
          <small>管理服务默认不会暴露 Bot Token、Chat ID 或模型密钥。</small>
        </form>
      </div>}
      {toast && <div className="toast"><span className="toast-icon"><Check size={15} /></span>{toast}<button onClick={() => setToast(null)}><X size={14} /></button></div>}
    </div>
  )
}

export default App

createRoot(document.getElementById('root')!).render(<App />)
