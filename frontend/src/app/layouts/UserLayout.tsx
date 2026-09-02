import { Outlet } from "react-router-dom";
import RoleHeader from "./RoleHeader";

export default function UserLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-cream">
      <RoleHeader zone="Кабинет пользователя" />
      <main className="min-h-0 flex-1"><Outlet /></main>
    </div>
  );
}
