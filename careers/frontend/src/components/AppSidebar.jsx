import { LogOut, BriefcaseBusiness, Search, MessageCircle, Settings, CircleHelp } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Tooltip, TooltipTrigger } from "react-aria-components";

import { parseWorkspaceSearch } from "../validation/forms";

function isNavItemActive(item, pathname) {
  if (item.to === "/applications") {
    return pathname === "/applications" || /^\/applications\/\d+(\/edit)?$/.test(pathname);
  }
  if (item.to === "/applications/ai-cv-matching") {
    return pathname === item.to;
  }
  if (item.to === "/hr/jobs") {
    return pathname === "/hr/jobs" || /^\/hr\/jobs\/\d+/.test(pathname);
  }
  if (item.to === "/hr/jobs/new") {
    return pathname === item.to;
  }
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function SidebarNavItem({ item, isCollapsed }) {
  const location = useLocation();
  const isActive = isNavItemActive(item, location.pathname);

  const navLink = (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      className={() =>
        `app-nav-link ${isCollapsed ? "app-nav-link--compact" : ""} ${isActive ? "is-active" : ""}`
      }
      aria-current={isActive ? "page" : undefined}
    >
      <item.icon className="h-5 w-5" aria-hidden="true" />
      <span className="app-nav-link__label">{item.label}</span>
    </NavLink>
  );

  if (!isCollapsed) {
    return navLink;
  }

  return (
    <TooltipTrigger delay={0} closeDelay={0}>
      {navLink}
      <Tooltip className="app-tooltip" offset={12} placement="right">
        {item.label}
      </Tooltip>
    </TooltipTrigger>
  );
}

function SidebarNavigation({ navItems, isCollapsed }) {
  const communicationItems = [
    { to: "/chat", label: "Chat", icon: MessageCircle },
  ];

  return (
    <div className="app-sidebar__nav-section-group">
      <div className="app-sidebar__nav-section">
        <div className="app-sidebar__nav-label">Main</div>
        <nav className="app-nav" aria-label="Workspace navigation">
          {navItems.map((item) => (
            <SidebarNavItem key={item.to} item={item} isCollapsed={isCollapsed} />
          ))}
        </nav>
      </div>

      <div className="app-sidebar__nav-section">
        <div className="app-sidebar__nav-label">Communication</div>
        <nav className="app-nav" aria-label="Communication">
          {communicationItems.map((item) => (
            <SidebarNavItem key={item.to} item={item} isCollapsed={isCollapsed} />
          ))}
        </nav>
      </div>
    </div>
  );
}

function SidebarSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    const parsed = parseWorkspaceSearch(query);
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    setError("");
    navigate(parsed.query ? `/search?q=${encodeURIComponent(parsed.query)}` : "/search");
  }

  return (
    <form className="app-sidebar__search" onSubmit={handleSubmit} role="search" aria-label="Search workspace">
      <div className="app-sidebar__search-input-wrapper">
        <Search className="h-4 w-4 app-sidebar__search-icon" />
        <input
          type="text"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setError("");
          }}
          placeholder="Search workspace"
          maxLength={80}
          className="app-sidebar__search-input"
          aria-label="Search workspace"
          aria-invalid={Boolean(error) || undefined}
        />
      </div>
      {error && <p className="app-sidebar__search-error">{error}</p>}
    </form>
  );
}

function SidebarHeader({ appLabel, isCollapsed }) {
  return (
    <div className={`app-sidebar__top ${isCollapsed ? "is-collapsed" : ""}`}>
      <div className={`app-brand ${isCollapsed ? "is-compact" : ""}`}>
        <span className="app-brand__mark" aria-hidden="true">
          <BriefcaseBusiness className="h-5 w-5" />
        </span>
        <div className="app-brand__text">
          <p>{appLabel}</p>
          <span>Workspace</span>
        </div>
      </div>
    </div>
  );
}

function SidebarAccount({ user, isCollapsed }) {
  if (!user) return null;

  return (
    <div className={`app-sidebar__account ${isCollapsed ? "is-compact" : ""}`}>
      <div className="account-avatar" aria-hidden="true">
        {(user.full_name || user.email || "T").charAt(0).toUpperCase()}
      </div>
      <div className="account-info">
        <p title={user.full_name || user.email}>{user.full_name || user.email || "Tide account"}</p>
        <span>{user.role}</span>
      </div>
    </div>
  );
}

export function AppSidebar({ user, navItems, appLabel, logout }) {
  const [isCollapsed] = useState(false);
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <aside
      className={`app-sidebar hidden lg:flex ${isCollapsed ? "is-collapsed" : ""}`}
    >
      <SidebarHeader
        appLabel={appLabel}
        isCollapsed={isCollapsed}
      />

      <SidebarSearch />

      <div className="app-sidebar__scroll-area">
        <SidebarNavigation navItems={navItems} isCollapsed={isCollapsed} />
      </div>

      <div className="app-sidebar__bottom">
        <nav className="app-nav app-sidebar__bottom-nav" aria-label="Settings and Help">
          <SidebarNavItem item={{ to: "/help", label: "Help", icon: CircleHelp }} isCollapsed={isCollapsed} />
          <SidebarNavItem item={{ to: "/settings", label: "Settings", icon: Settings }} isCollapsed={isCollapsed} />
        </nav>

        <SidebarAccount user={user} isCollapsed={isCollapsed} />

        {isCollapsed ? (
          <TooltipTrigger delay={0} closeDelay={0}>
            <button
              type="button"
              onClick={handleLogout}
              className="app-sidebar__logout app-sidebar__logout--compact"
              aria-label="Sign out"
            >
              <LogOut className="h-5 w-5" aria-hidden="true" />
            </button>
            <Tooltip className="app-tooltip" offset={12} placement="right">
              Sign out
            </Tooltip>
          </TooltipTrigger>
        ) : (
          <button
            type="button"
            onClick={handleLogout}
            className="app-sidebar__logout"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            <span>Sign out</span>
          </button>
        )}
      </div>
    </aside>
  );
}
