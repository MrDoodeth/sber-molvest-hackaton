import { Outlet } from "react-router-dom";
import RoleHeader from "./RoleHeader";

export default function OperatorLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-cream">
      <RoleHeader zone="Рабочее место оператора" dark></RoleHeader>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
