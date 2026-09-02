import { Headphones } from "lucide-react";
import { Outlet } from "react-router-dom";
import RoleHeader from "./RoleHeader";

export default function OperatorLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-100">
      <RoleHeader zone="Рабочее место оператора" dark>
        <span className="hidden items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-molvest-100 md:flex"><Headphones className="size-3.5" /> Линия поддержки</span>
      </RoleHeader>
      <main className="min-h-0 flex-1"><Outlet /></main>
    </div>
  );
}
