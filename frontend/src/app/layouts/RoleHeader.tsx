import type { ReactNode } from "react";
import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../shared/ui";
import { cn } from "../../shared/utils";

const logoUrl = "/molvest-logo.png";

export function MolvestMark({ inverse = false }: { inverse?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className={cn("relative flex size-10 items-center justify-center overflow-hidden rounded-xl bg-[linear-gradient(135deg,#2b9ffe,#fbc4fb)] font-black text-white", inverse && "shadow-[0_0_0_1px_rgb(255_255_255/20%)]")}>
        <img className="size-full object-cover" src={logoUrl} alt="Молвест" />
      </span>
      <span className="leading-tight">
        <strong className="block text-sm tracking-[0.08em]">МОЛВЕСТ</strong>
        <span className={cn("text-[10px] uppercase tracking-[0.16em]", inverse ? "text-[#8ea3c8]" : "text-slate-500")}>Поддержка 1С</span>
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

  return (
    <header className={cn("z-30 border-b px-4 py-3 sm:px-[22px]", dark ? "border-white/10 bg-black text-white" : "border-[#dbe3f0] bg-white/95 text-black backdrop-blur")}>
      <div className="flex w-full items-center justify-between gap-4">
        <div className="flex items-center gap-4 sm:gap-7">
          <MolvestMark inverse={dark} />
          <span className={cn("hidden border-l pl-5 text-sm font-bold sm:block", dark ? "border-white/20 text-white" : "border-[#dbe3f0] text-slate-600")}>{zone}</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          {children}
          <div className="hidden text-right sm:block">
            <p className="text-sm font-bold">Демо-режим</p>
            <p className={cn("text-[10px] uppercase tracking-wider", dark ? "text-[#8ea3c8]" : "text-slate-400")}>{zone}</p>
          </div>
          <Button
            type="button"
            variant={dark ? "secondary" : "ghost"}
            size="sm"
            onClick={() => navigate("/")}
            aria-label="Выйти"
          >
            <LogOut className="size-4" />
            <span className="hidden sm:inline">Выйти</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
