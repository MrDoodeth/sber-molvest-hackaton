import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError } from "../../api/client";
import { authApi } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import type { Role } from "../../api/types";
import { Button, ErrorState, PageLoader } from "../../shared/ui";

const rolePaths: Record<Role, string> = { user: "/user", operator: "/operator", admin: "/admin" };
const roleNames: Record<Role, string> = { user: "пользователя", operator: "оператора", admin: "администратора" };

export default function RoleGuard({ allow, children }: { allow: Role; children: ReactNode }) {
  const location = useLocation();
  const me = useQuery({ queryKey: queryKeys.me(), queryFn: ({ signal }) => authApi.me(signal), retry: false });

  if (me.isPending) return <PageLoader label="Проверяем доступ" />;
  if (me.error instanceof ApiError && me.error.status === 401) {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }
  if (me.isError) {
    return <ErrorState description={me.error.message} onRetry={() => void me.refetch()} />;
  }
  if (me.data.role !== allow) {
    return (
      <main className="flex min-h-screen items-center justify-center p-5">
        <div className="max-w-lg rounded-3xl border border-molvest-100 bg-white p-8 text-center shadow-xl">
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-red-700">Доступ ограничен</p>
          <h1 className="mt-3 text-2xl font-bold text-molvest-950">Это зона {roleNames[allow]}</h1>
          <p className="mt-3 text-sm leading-6 text-stone-500">Вы вошли как «{me.data.displayName}». Роль повторно проверяется backend на каждом запросе.</p>
          <Button className="mt-6" onClick={() => window.location.assign(rolePaths[me.data.role])}>Перейти в свою панель</Button>
        </div>
      </main>
    );
  }
  return <>{children}</>;
}
