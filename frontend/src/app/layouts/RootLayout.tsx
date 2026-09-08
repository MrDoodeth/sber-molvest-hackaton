import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { AUTH_EXPIRED_EVENT } from "../../api/client";

export default function RootLayout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    const handleExpiredSession = () => {
      queryClient.clear();
      navigate("/", { replace: true });
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpiredSession);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpiredSession);
  }, [navigate, queryClient]);

  return <Outlet />;
}
