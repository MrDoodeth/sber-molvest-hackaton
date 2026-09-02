import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../../api/auth";
import { queryKeys } from "../../api/queryKeys";
import { Button, useToast } from "../../shared/ui";
import { cn } from "../../shared/utils";

export function MolvestMark({ inverse = false }: { inverse?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className={cn("relative flex size-10 items-center justify-center overflow-hidden rounded-2xl font-black", inverse ? "bg-white text-molvest-800" : "bg-molvest-800 text-white")}>
        M<span className="absolute -bottom-2 -right-1 size-5 rotate-45 bg-red-600" />
      </span>
      <span className="leading-tight">
        <strong className="block text-sm tracking-[0.08em]">МОЛВЕСТ</strong>
        <span className={cn("text-[10px] uppercase tracking-[0.16em]", inverse ? "text-molvest-100" : "text-stone-500")}>Поддержка 1С</span>
      </span>
    </div>
  );
}

export default function RoleHeader({
  zone,
  children,
  dark = false,
}: {
  zone: string;
  children?: ReactNode;
  dark?: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const me = useQuery({ queryKey: queryKeys.me(), queryFn: ({ signal }) => authApi.me(signal) });
  const logout = useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      queryClient.clear();
      navigate("/", { replace: true });
    },
    onError: (error) => toast(error.message, "error"),
  });
  return (
    <header className={cn("z-30 border-b px-4 py-3 sm:px-6", dark ? "border-white/10 bg-molvest-950 text-white" : "border-molvest-100 bg-white/95 text-molvest-950 backdrop-blur")}>
      <div className="flex w-full items-center justify-between gap-4">
        <div className="flex items-center gap-4 sm:gap-7">
          <MolvestMark inverse={dark} />
          <span className={cn("hidden border-l pl-5 text-sm font-bold sm:block", dark ? "border-white/15 text-molvest-100" : "border-stone-200 text-stone-600")}>{zone}</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          {children}
          <div className="hidden text-right sm:block">
            <p className="text-sm font-bold">{me.data?.displayName}</p>
            <p className={cn("text-[10px] uppercase tracking-wider", dark ? "text-molvest-200" : "text-stone-400")}>{zone}</p>
          </div>
          <Button type="button" variant={dark ? "secondary" : "ghost"} size="sm" pending={logout.isPending} onClick={() => logout.mutate()} aria-label="Выйти">
            <LogOut className="size-4" /><span className="hidden sm:inline">Выйти</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
