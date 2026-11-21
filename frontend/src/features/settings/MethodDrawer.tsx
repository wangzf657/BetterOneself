import { Sheet } from "@/components/ui/dialog";

const METHODS: { title: string; body: string; where: string }[] = [
  {
    title: "先见森林",
    body: "先说出这本书整体讲什么、分几部分怎么推进，再学细节；学任何节点前先知道它在全书里的位置。",
    where: "出现在技能树总述与会话开场。依据《如何阅读一本书》分析阅读。",
  },
  {
    title: "先答再看",
    body: "先自己回答，再看反馈；“想起来”比“再看一遍”更能暴露真实掌握。",
    where: "出现在节点测验。",
  },
  {
    title: "过关才点亮",
    body: "通过本节点测验才点亮。点亮代表当前通过，不承诺长期记忆。",
    where: "出现在技能树。",
  },
  {
    title: "引导你思考",
    body: "先给提示，让你自己走完推理；也可切到直接讲解。",
    where: "出现在「带我学」。",
  },
  {
    title: "直接讲给我",
    body: "时间紧或只需理解时，直接给清楚解释，不强行绕弯。",
    where: "出现在「讲给我听」。",
  },
  {
    title: "高密度考练",
    body: "练习频率与考练密度更高，用通过测验倒逼掌握；只改变密度，不改变通过线。",
    where: "出现在「帮我过关」。",
  },
];

/** 学习方法抽屉（全站，页面清单）：大白话 + 在哪里 + 一句依据。 */
export default function MethodDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="学习方法" width={440}>
      <div className="space-y-3">
        {METHODS.map((m) => (
          <div key={m.title} className="rounded-lg border bg-white p-4">
            <div className="font-medium">{m.title}</div>
            <p className="mt-1 text-sm text-ink-soft">{m.body}</p>
            <p className="mt-1.5 text-xs text-ink-soft/80">{m.where}</p>
          </div>
        ))}
      </div>
    </Sheet>
  );
}
