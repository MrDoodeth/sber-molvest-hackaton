import {
  BarChart3,
  BookOpen,
  MessagesSquare,
  Settings2,
  SlidersHorizontal,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import RoleHeader from "./RoleHeader";
import { cn } from "../../shared/utils";

const links = [
  { to: "/admin/dialogs", label: "Журнал обращений", icon: MessagesSquare },
  { to: "/admin/knowledge", label: "База знаний", icon: BookOpen },
  { to: "/admin/prompts", label: "Системные промпты", icon: SlidersHorizontal },
  { to: "/admin/settings", label: "Настройки AI", icon: Settings2 },
  { to: "/admin/monitoring", label: "Мониторинг", icon: BarChart3 },
];

export default function AdminLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-cream">
      <RoleHeader zone="Администрирование" dark />
      <div className="mx-auto flex min-h-0 w-full max-w-[1720px] flex-1 flex-col lg:flex-row">
        <aside className="border-b border-[#dbe3f0] bg-white lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r">
          <nav
            aria-label="Разделы администрирования"
            className="flex gap-1 overflow-x-auto p-2 lg:grid lg:p-4"
          >
            {links.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 shrink-0 items-center gap-3 rounded-xl px-3.5 text-sm font-semibold transition",
                    isActive
                      ? "bg-black text-white shadow-sm"
                      : "text-slate-600 hover:bg-[#f1f4fb] hover:text-black",
                  )
                }
              >
                <Icon className="size-4" /> {label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
