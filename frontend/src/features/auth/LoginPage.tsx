import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Bot, Headphones, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import type { Role } from "../../api/types";
import { Button } from "../../shared/ui";
import { cn } from "../../shared/utils";
import { MolvestMark } from "../../app/layouts/RoleHeader";

const roleCards: Array<{ role: Role; title: string; description: string; icon: typeof Bot; accent: string }> = [
  { role: "user", title: "Пользователь 1С", description: "Задать вопрос, приложить скриншот и получить решение.", icon: Bot, accent: "bg-molvest-100 text-molvest-700" },
  { role: "operator", title: "Оператор", description: "Принять эскалацию и работать с черновиком GigaChat.", icon: Headphones, accent: "bg-[#fbc4fb]/55 text-[#a13cc9]" },
  { role: "admin", title: "Администратор", description: "Управлять знаниями, качеством и настройками AI.", icon: ShieldCheck, accent: "bg-[#fcc67f]/45 text-[#9a5600]" },
];
const rolePath: Record<Role, string> = { user: "/user", operator: "/operator", admin: "/admin/dialogs" };

export default function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedRole, setSelectedRole] = useState<Role>();
  const login = useMutation({
    mutationFn: async (role: Role) => {
      await authApi.demoLogin(role);
      return authApi.me();
    },
    onMutate: (role) => setSelectedRole(role),
    onSuccess: (user) => {
      queryClient.clear();
      queryClient.setQueryData(queryKeys.me(), user);
      navigate(rolePath[user.role]);
    },
    onSettled: () => setSelectedRole(undefined),
  });
  const me = queryClient.getQueryData<{ role: Role; displayName: string }>(queryKeys.me());

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f7f9fd] px-4 py-6 sm:px-8 sm:py-10">
      <div className="absolute -right-40 -top-36 size-[34rem] rounded-full bg-molvest-200/45 blur-3xl" aria-hidden="true" />
      <div className="absolute -bottom-48 -left-36 size-[30rem] rounded-full bg-[#fbc4fb]/45 blur-3xl" aria-hidden="true" />
      <div className="relative mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col">
        <header className="flex items-center justify-between">
          <MolvestMark />
          <span className="rounded-full border border-[#dbe3f0] bg-white/80 px-3 py-1.5 text-xs font-bold text-slate-600 backdrop-blur">Демонстрационный контур</span>
        </header>
        <section className="my-auto grid items-center gap-10 py-12 lg:grid-cols-[0.88fr_1.12fr] lg:gap-16">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-[0.23em] text-molvest-700">AI-агент техподдержки</p>
            <h1 className="mt-4 max-w-xl text-4xl font-black leading-[1.06] tracking-[-0.045em] text-black sm:text-6xl">1С без долгого ожидания.</h1>
            <p className="mt-6 max-w-lg text-base leading-7 text-slate-500 sm:text-lg">GigaChat ищет решение в базе знаний «Молвест», анализирует скриншоты и вовремя подключает специалиста.</p>
            <div className="mt-8 flex flex-wrap gap-3 text-xs font-bold text-molvest-700">
              <span className="rounded-full bg-white px-3 py-2 shadow-sm">RAG по документации 1С</span>
              <span className="rounded-full bg-white px-3 py-2 shadow-sm">Vision-анализ</span>
              <span className="rounded-full bg-white px-3 py-2 shadow-sm">Один непрерывный тикет</span>
            </div>
          </div>
          <div className="rounded-[28px] border border-[#dbe3f0] bg-white/90 p-4 shadow-[0_30px_70px_rgb(31_58_100/18%)] backdrop-blur sm:p-6">
            <div className="mb-5 flex items-end justify-between gap-4 px-1">
              <div>
                <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-700">Вход без пароля</p>
                <h2 className="mt-1 text-2xl font-bold text-black">Выберите роль</h2>
              </div>
              {me && <Button size="sm" onClick={() => navigate(rolePath[me.role])}>Продолжить <ArrowRight className="size-4" /></Button>}
            </div>
            <div className="grid gap-3">
              {roleCards.map(({ role, title, description, icon: Icon, accent }) => (
                  <button
                    key={role}
                    type="button"
                    disabled={login.isPending}
                    onClick={() => login.mutate(role)}
                    className="group flex items-center gap-4 rounded-2xl border border-[#dbe3f0] bg-white p-4 text-left transition hover:-translate-y-0.5 hover:border-molvest-400 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-molvest-400 disabled:opacity-60 sm:p-5"
                  >
                    <span className={cn("flex size-12 shrink-0 items-center justify-center rounded-2xl", accent)}><Icon className="size-5" /></span>
                    <span className="min-w-0 flex-1">
                      <strong className="block text-base text-black">{title}</strong>
                      <span className="mt-1 block text-sm leading-5 text-slate-500">{description}</span>
                    </span>
                    {login.isPending && selectedRole === role ? <span className="text-xs font-bold text-molvest-700">Входим…</span> : <ArrowRight className="size-5 text-slate-300 transition group-hover:translate-x-1 group-hover:text-molvest-700" />}
                  </button>
              ))}
            </div>
            {login.isError && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-800" role="alert">{login.error.message}</p>}
            <p className="mt-5 px-1 text-xs leading-5 text-slate-400">Сессия хранится в защищённой HttpOnly cookie. Токены и ключи GigaChat не передаются браузеру.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
