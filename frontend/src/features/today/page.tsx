import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api, type Schemas } from '@/lib/api'

/** 今日任务页(M5-01/03):M1 为壳——空态引导 + 活跃项目快捷;完整形态随 M3 上线 */
export function TodayPage() {
  const { data: studies } = useQuery({
    queryKey: ['studies'],
    queryFn: () => api<Schemas['StudyOut'][]>('/api/studies'),
  })
  const active = studies ?? []

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="mb-1 text-2xl font-semibold">今天该做什么</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        {active.length === 0
          ? '还没有学习项目——从一个开始。'
          : '学习计划尚未生成(目标访谈在里程碑 3 上线);先去导入资料、看看拆出的知识点。'}
      </p>

      {active.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">新建学习项目</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p>输入名称与一句话目标,然后导入你的第一份资料。</p>
            <Link
              to="/studies"
              className="mt-3 inline-block rounded-md bg-primary px-4 py-2 text-primary-foreground"
            >
              去创建
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {active.map((s) => (
            <Link key={s.id} to={`/studies/${s.id}/sources`}>
              <Card className="transition-colors hover:bg-accent/40">
                <CardHeader>
                  <CardTitle className="text-base">{s.name}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{s.goal}</CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </main>
  )
}
