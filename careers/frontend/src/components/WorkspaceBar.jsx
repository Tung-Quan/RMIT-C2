import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function WorkspaceBar() {
  const { user } = useAuth();
  return <nav className="fairenrol-workspace-bar" aria-label="FairEnrol workspaces">
    <a href="/" className="fairenrol-workspace-brand">F <span>FairEnrol</span></a>
    <a href="/">Courses</a>
    <Link to="/candidate/dashboard">My career</Link>
    {user?.role === "hr" && <Link to="/hr/dashboard">Hiring workspace</Link>}
    <span className="fairenrol-identity">TideCloak · {user?.full_name || "Secure sign-in"}</span>
  </nav>;
}
