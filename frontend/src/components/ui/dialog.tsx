import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[520px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-white p-6 shadow-xl focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded p-1 text-ink-soft hover:bg-black/5">
          <X size={16} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({ title, desc }: { title: React.ReactNode; desc?: React.ReactNode }) {
  return (
    <div className="mb-4">
      <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
      {desc && (
        <DialogPrimitive.Description className="mt-1 text-sm text-ink-soft">
          {desc}
        </DialogPrimitive.Description>
      )}
    </div>
  );
}

/** 侧边抽屉（学习方法 / 结构记录）。 */
export function Sheet({
  open,
  onOpenChange,
  side = "right",
  title,
  width = 480,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  side?: "right" | "left";
  title: React.ReactNode;
  width?: number;
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/30" />
        <DialogPrimitive.Content
          style={{ width }}
          className={cn(
            "fixed inset-y-0 z-50 flex max-w-[92vw] flex-col border-line bg-white shadow-xl focus:outline-none",
            side === "right" ? "right-0 border-l" : "left-0 border-r",
          )}
        >
          <div className="flex h-14 items-center justify-between border-b px-5">
            <DialogPrimitive.Title className="font-semibold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="rounded p-1 text-ink-soft hover:bg-black/5">
              <X size={16} />
            </DialogPrimitive.Close>
          </div>
          <div className="flex-1 overflow-y-auto p-5">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
