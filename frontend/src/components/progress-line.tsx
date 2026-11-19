/** 导入/拆解进度条(M1-06):阶段文案 + 批次进度,随轮询数据刷新 */
export function ProgressLine({
  stage,
  current,
  total,
}: {
  stage: string
  current: number
  total: number | null
}) {
  const label =
    stage === 'parsing'
      ? '解析文档中…(视文件大小可能数分钟)'
      : stage === 'embedding'
        ? `向量化 ${current}/${total ?? '?'} 批`
        : `拆解知识点 ${current}/${total ?? '?'} 批`
  const pct = total ? Math.min(100, Math.round((current / total) * 100)) : null
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span>{label}</span>
      {pct !== null && (
        <div className="h-1.5 w-32 overflow-hidden rounded bg-muted">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}
