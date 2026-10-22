import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export function getRoleHomePath(role) {
  if (role === "hr") return "/hr/dashboard";
  return "/candidate/dashboard";
}

export function RoleHomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={getRoleHomePath(user?.role)} replace />;
}
