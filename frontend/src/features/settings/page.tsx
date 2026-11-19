import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'

interface SettingsShape {
  llm_base_url: string | null
  llm_model: string | null
  llm_key_set: boolean
  embed_base_url: string | null
  embed_model: string | null
  embed_key_set: boolean
  daily_review_limit: number
  inactivity_threshold_days: number
}

interface UsageRow {
  date: string
  scene: string
  prompt_tokens: number
  completion_tokens: number
  requests: number
}

const SCENE_LABEL: Record<string, string> = {
  chat: '对话',
  decompose: '拆解',
  quiz: '测验',
  embed: '向量化',
}

/** 设置(M7-01~04):BYO-Key 掩码存储、复习上限、中断阈值、用量、全量导出 */
export function SettingsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api<SettingsShape>('/api/settings'),
  })
  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => api<UsageRow[]>('/api/usage'),
  })

  if (isLoading || !data) return <Skeleton className="h-96 w-full" />
  return <SettingsForm seed={data} usage={usage ?? []} />
}

function SettingsForm({ seed, usage }: { seed: SettingsShape; usage: UsageRow[] }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    llm_base_url: seed.llm_base_url ?? '',
    llm_model: seed.llm_model ?? '',
    llm_api_key: '',
    embed_base_url: seed.embed_base_url ?? '',
    embed_model: seed.embed_model ?? '',
    embed_api_key: '',
    daily_review_limit: seed.daily_review_limit,
    inactivity_threshold_days: seed.inactivity_threshold_days,
  })

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        llm_base_url: form.llm_base_url || null,
        llm_model: form.llm_model || null,
        embed_base_url: form.embed_base_url || null,
        embed_model: form.embed_model || null,
        daily_review_limit: form.daily_review_limit,
        inactivity_threshold_days: form.inactivity_threshold_days,
      }
      if (form.llm_api_key) payload.llm_api_key = form.llm_api_key // 只在填写时更新
      if (form.embed_api_key) payload.embed_api_key = form.embed_api_key
      return api<SettingsShape>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) })
    },
    onSuccess: () => {
      toast.success('设置已保存(key 加密落库)')
      setForm((f) => ({ ...f, llm_api_key: '', embed_api_key: '' }))
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="mx-auto max-w-2xl space-y-6" data-testid="settings-page">
      <h1 className="text-2xl font-semibold">设置</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">模型配置(BYO-Key)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="对话模型 base_url">
            <Input
              value={form.llm_base_url}
              onChange={(e) => setForm({ ...form, llm_base_url: e.target.value })}
              placeholder="https://open.bigmodel.cn/api/coding/paas/v4"
            />
          </Field>
          <Field label="对话模型名">
            <Input
              value={form.llm_model}
              onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
              placeholder="glm-5.3-flash"
            />
          </Field>
          <Field
            label="对话 API Key"
            hint={seed.llm_key_set ? '已设置(加密存储)——留空保持不变' : undefined}
          >
            <Input
              type="password"
              value={form.llm_api_key}
              onChange={(e) => setForm({ ...form, llm_api_key: e.target.value })}
              placeholder="sk-…"
            />
          </Field>
          <Field label="Embedding base_url">
            <Input
              value={form.embed_base_url}
              onChange={(e) => setForm({ ...form, embed_base_url: e.target.value })}
              placeholder="https://api.siliconflow.cn/v1"
            />
          </Field>
          <Field label="Embedding 模型名">
            <Input
              value={form.embed_model}
              onChange={(e) => setForm({ ...form, embed_model: e.target.value })}
              placeholder="BAAI/bge-m3"
            />
          </Field>
          <Field
            label="Embedding API Key"
            hint={seed.embed_key_set ? '已设置(加密存储)——留空保持不变' : undefined}
          >
            <Input
              type="password"
              value={form.embed_api_key}
              onChange={(e) => setForm({ ...form, embed_api_key: e.target.value })}
              placeholder="sk-…"
            />
          </Field>
          <Field label="复习每日上限(张)">
            <Input
              type="number"
              min={5}
              max={200}
              value={form.daily_review_limit}
              onChange={(e) => setForm({ ...form, daily_review_limit: Number(e.target.value) })}
            />
          </Field>
          <Field label="中断阈值(天)">
            <Input
              type="number"
              min={2}
              max={60}
              value={form.inactivity_threshold_days}
              onChange={(e) =>
                setForm({ ...form, inactivity_threshold_days: Number(e.target.value) })
              }
            />
          </Field>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? '保存中…' : '保存设置'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">用量与成本(M7-04)</CardTitle>
        </CardHeader>
        <CardContent>
          {usage.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无调用记录(stub/未配置)。</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">日期</th>
                  <th>场景</th>
                  <th className="text-right">请求</th>
                  <th className="text-right">输入 tok</th>
                  <th className="text-right">输出 tok</th>
                </tr>
              </thead>
              <tbody>
                {usage.slice(0, 15).map((r) => (
                  <tr key={`${r.date}-${r.scene}`} className="border-t">
                    <td className="py-1">{r.date}</td>
                    <td>{SCENE_LABEL[r.scene] ?? r.scene}</td>
                    <td className="text-right">{r.requests}</td>
                    <td className="text-right">{r.prompt_tokens}</td>
                    <td className="text-right">{r.completion_tokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">数据备份与导出(M7-02/03)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-muted-foreground">
            数据存本地 SQLite(backend/data/app.db),重启不丢;备份=拷贝该文件。亦可用下方全量导出。
          </p>
          <a
            href="/api/export"
            download
            className="inline-block rounded-md border px-3 py-1.5 hover:bg-accent/50"
          >
            全量导出(JSON)
          </a>
        </CardContent>
      </Card>
    </div>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  )
}
