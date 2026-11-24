import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { client, errDetail, type SettingsPayload } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Badge, Input, Label } from "@/components/ui/basics";

const SCENE_LABEL: Record<string, string> = {
  outline: "AI 规划",
  tutor: "讲解与问答",
  quiz: "出题与评语",
  embed: "资料向量化",
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings } = useQuery<SettingsPayload>({
    queryKey: ["settings"],
    queryFn: async () => {
      const res = await client.GET("/api/settings");
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });

  const save = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const res = await client.PUT("/api/settings", { body: body as never });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已保存");
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="text-2xl font-bold">设置</h1>

      <section className="mt-6 rounded-lg border bg-white p-6">
        <h2 className="font-semibold">讲解与测验服务</h2>
        <p className="mt-1 text-xs text-ink-soft">OpenAI 兼容协议；密钥加密保存在本机，界面只显示掩码。</p>
        <ServiceForm
          group="llm"
          values={settings?.llm}
          placeholders={["https://api.example.com/v1", "模型名，如 glm-4.7"]}
          saving={save.isPending}
          onSave={(body) => save.mutate(body)}
        />
      </section>

      <section className="mt-4 rounded-lg border bg-white p-6">
        <h2 className="flex items-center gap-2 font-semibold">
          资料处理服务（embedding）
          {settings?.embed.status && <Badge tone={settings.embed.status === "ready" ? "gold" : "amber"}>{embedStatusText(settings.embed.status)}</Badge>}
        </h2>
        <p className="mt-1 text-xs text-ink-soft">{settings?.embed.note ?? "用于准备可回跳的跨节点检索。"}</p>
        {settings?.embed.error && (
          <p className="mt-1 text-xs text-red-600">{settings.embed.error}</p>
        )}
        <ServiceForm
          group="embed"
          values={settings?.embed}
          placeholders={["https://api.siliconflow.cn/v1", "BAAI/bge-m3"]}
          saving={save.isPending}
          onSave={(body) => save.mutate(body)}
        />
      </section>

      <UsageSection />
      <FeedbackSection />
      <DangerSection />
    </div>
  );
}

function embedStatusText(s: string): string {
  return (
    {
      pending: "等待中",
      running: "进行中",
      ready: "就绪",
      degraded: "降级",
      failed: "失败",
      precheck_failed: "预检失败",
    } as Record<string, string>
  )[s] ?? s;
}

function ServiceForm({
  group,
  values,
  placeholders,
  saving,
  onSave,
}: {
  group: "llm" | "embed";
  values?: { base_url?: string | null; model?: string | null; api_key?: string | null };
  placeholders: [string, string];
  saving: boolean;
  onSave: (body: Record<string, unknown>) => void;
}) {
  // 掩码不回写为实际值：仅在用户改动时提交新值；置空即清除（P1-06）
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  useEffect(() => {
    setBaseUrl(values?.base_url ?? "");
    setModel(values?.model ?? "");
    setApiKey("");
    setClearKey(false);
  }, [values?.base_url, values?.model, values?.api_key]);

  const dirty =
    baseUrl.trim() !== (values?.base_url ?? "") ||
    model.trim() !== (values?.model ?? "") ||
    (clearKey ? !!values?.api_key : apiKey.trim() !== "" && apiKey !== values?.api_key);

  const buildBody = (): Record<string, unknown> => {
    const inner: Record<string, unknown> = {};
    if (baseUrl.trim() !== (values?.base_url ?? "")) inner.base_url = baseUrl.trim() || null;
    if (model.trim() !== (values?.model ?? "")) inner.model = model.trim() || null;
    if (clearKey) inner.api_key = null;
    else if (apiKey.trim() && apiKey !== values?.api_key) inner.api_key = apiKey.trim();
    return { [group]: inner };
  };

  return (
    <div className="mt-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>服务地址</Label>
          <Input placeholder={placeholders[0]} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </div>
        <div>
          <Label>模型</Label>
          <Input placeholder={placeholders[1]} value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
      </div>
      <div>
        <Label>API Key</Label>
        <Input
          type="password"
          placeholder={values?.api_key ? "已保存（如需替换请输入新值）" : "sk-…（保存后只显示掩码）"}
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.target.value);
            setClearKey(false);
          }}
        />
        <div className="mt-1 flex items-center gap-2 text-xs text-ink-soft">
          {values?.api_key ? <>当前：{values.api_key}</> : "未设置"}
          {!!values?.api_key && (
            <button
              className={clearKey ? "font-medium text-red-600" : "text-red-600 hover:underline"}
              onClick={() => setClearKey(true)}
              disabled={clearKey}
            >
              {clearKey ? "将在保存时清除" : "清除密钥"}
            </button>
          )}
        </div>
      </div>
      <div className="flex justify-end">
        <Button size="sm" disabled={saving || !dirty} onClick={() => onSave(buildBody())}>
          保存本节
        </Button>
      </div>
    </div>
  );
}

function UsageSection() {
  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: async () => {
      const res = await client.GET("/api/usage");
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });
  return (
    <section className="mt-4 rounded-lg border bg-white p-6">
      <h2 className="font-semibold">用量</h2>
      {!usage || usage.length === 0 ? (
        <p className="mt-2 text-sm text-ink-soft">
          还没有 AI 用量——配置服务并开始学习后，这里会按日期与场景显示请求和 token 消耗。
        </p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead className="text-xs text-ink-soft">
            <tr className="border-b text-left">
              <th className="py-1.5 font-normal">日期</th>
              <th className="font-normal">场景</th>
              <th className="font-normal">请求</th>
              <th className="font-normal">prompt tokens</th>
              <th className="font-normal">completion tokens</th>
            </tr>
          </thead>
          <tbody>
            {usage.map((u, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1.5">{u.date}</td>
                <td>{SCENE_LABEL[u.scene] ?? u.scene}</td>
                <td>{u.requests}</td>
                <td>{u.prompt_tokens}</td>
                <td>{u.completion_tokens}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function FeedbackSection() {
  const [sound, setSound] = useState(() => localStorage.getItem("bo.sound") === "1");
  const [effects, setEffects] = useState(() => localStorage.getItem("bo.effects") !== "0");
  return (
    <section className="mt-4 rounded-lg border bg-white p-6">
      <h2 className="font-semibold">点亮反馈</h2>
      <div className="mt-3 space-y-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={sound}
            onChange={(e) => {
              setSound(e.target.checked);
              localStorage.setItem("bo.sound", e.target.checked ? "1" : "0");
            }}
          />
          点亮音效（默认关闭）
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={effects}
            onChange={(e) => {
              setEffects(e.target.checked);
              localStorage.setItem("bo.effects", e.target.checked ? "1" : "0");
              document.documentElement.style.setProperty("--ritual-enabled", e.target.checked ? "1" : "0");
            }}
          />
          粒子与流光动效（默认开启；系统“减少动态效果”时自动降级）
        </label>
      </div>
    </section>
  );
}

function DangerSection() {
  const qc = useQueryClient();
  const clear = useMutation({
    mutationFn: async () => {
      const res = await client.PUT("/api/settings", {
        body: {
          llm: { base_url: null, model: null, api_key: null },
          embed: { base_url: null, model: null, api_key: null },
        },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已清除服务配置（含密钥）");
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const [confirm, setConfirm] = useState(false);
  return (
    <section className="mt-4 rounded-lg border border-red-200 bg-red-50/40 p-6">
      <h2 className="flex items-center gap-2 font-semibold text-red-700">
        <AlertTriangle size={16} /> 危险操作
      </h2>
      <p className="mt-1 text-xs text-ink-soft">
        清除服务配置会同时删除已保存的密钥；删除单本书的入口在书架与书页（弹影响清单、输入书名确认）。
      </p>
      {!confirm ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={() => setConfirm(true)}>
          清除服务配置（含密钥）
        </Button>
      ) : (
        <div className="mt-3 flex gap-2">
          <Button variant="danger" size="sm" disabled={clear.isPending} onClick={() => clear.mutate()}>
            确认清除
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>
            取消
          </Button>
        </div>
      )}
    </section>
  );
}
