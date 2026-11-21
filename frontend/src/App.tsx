import { HelpCircle } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import MethodDrawer from "./features/settings/MethodDrawer";

export default function App() {
  const [methodsOpen, setMethodsOpen] = useState(false);
  const loc = useLocation();
  // 学习会话是全屏三框，不显示全局顶栏
  const isLearn = /\/learn\//.test(loc.pathname);
  if (isLearn) return <Outlet />;

  return (
    <div className="min-h-screen">
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-4 border-b bg-white/90 px-8 backdrop-blur">
        <Link to="/studies" className="text-lg font-bold tracking-wide">
          BetterOneself
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <NavLink
            to="/studies"
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 ${isActive ? "bg-ink text-white" : "text-ink-soft hover:bg-black/5"}`
            }
          >
            我的书
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <button
            className="flex items-center gap-1 rounded-md px-3 py-1.5 text-ink-soft hover:bg-black/5"
            onClick={() => setMethodsOpen(true)}
          >
            <HelpCircle size={16} /> 学习方法
          </button>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 ${isActive ? "bg-ink text-white" : "text-ink-soft hover:bg-black/5"}`
            }
          >
            设置
          </NavLink>
        </div>
      </header>
      <main className="pt-14">
        <Outlet />
      </main>
      <MethodDrawer open={methodsOpen} onOpenChange={setMethodsOpen} />
    </div>
  );
}
