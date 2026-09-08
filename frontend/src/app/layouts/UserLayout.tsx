import { Outlet } from "react-router-dom";
import { UserProcessingProvider } from "../../shared/hooks/useUserProcessing";
import RoleHeader from "./RoleHeader";

export default function UserLayout() {
  return (
    <UserProcessingProvider>
      <div className="flex min-h-screen flex-col bg-cream">
        <RoleHeader zone="Кабинет пользователя" dark />
        <main className="min-h-0 flex-1"><Outlet /></main>
      </div>
    </UserProcessingProvider>
  );
}
