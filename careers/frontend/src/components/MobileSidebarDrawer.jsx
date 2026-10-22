import { LogOut, X, BriefcaseBusiness, MessageCircle, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { parseWorkspaceSearch } from "../validation/forms";

function MobileLinkBrand({ appLabel }) {
  return (
    <div className="app-brand">
      <span className="app-brand__mark" aria-hidden="true">
        <BriefcaseBusiness className="h-5 w-5" />
      </span>
      <div className="app-brand__text">
        <p>{appLabel}</p>
        <span>Workspace</span>
      </div>
    </div>
  );
}

function MobileSidebarNavItem({ item, onClose }) {
  const location = useLocation();
  const isActive =
    (item.to === "/applications" && (location.pathname === "/applications" || /^\/applications\/\d+(\/edit)?$/.test(location.pathname))) ||
    (item.to === "/applications/ai-cv-matching" && location.pathname === item.to) ||
    (item.to === "/hr/jobs" && (location.pathname === "/hr/jobs" || /^\/hr\/jobs\/\d+/.test(location.pathname))) ||
    (item.to === "/hr/jobs/new" && location.pathname === item.to) ||
    (location.pathname === item.to || location.pathname.startsWith(`${item.to}/`));

  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      onClick={onClose}
      className={() => `app-nav-link ${isActive ? "is-active" : ""}`}
      aria-current={isActive ? "page" : undefined}
    >
      <item.icon className="h-5 w-5" aria-hidden="true" />
      <span className="app-nav-link__label">{item.label}</span>
    </NavLink>
  );
}

export function MobileSidebarDrawer({ isOpen, onClose, user, navItems, appLabel, logout }) {
  const drawerRef = useRef(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      // Focus management: try to focus the close button when opened
      setTimeout(() => {
        const closeBtn = drawerRef.current?.querySelector('button[aria-label="Close navigation"]');
        closeBtn?.focus();
      }, 50);
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  function handleLogout() {
    logout();
    onClose();
    navigate("/login");
  }

  function handleSearchSubmit(event) {
    event.preventDefault();
    const parsed = parseWorkspaceSearch(query);
    if (parsed.error) {
      setSearchError(parsed.error);
      return;
    }
    setSearchError("");
    onClose();
    navigate(parsed.query ? `/search?q=${encodeURIComponent(parsed.query)}` : "/search");
  }

  if (!isOpen) return null;

  const communicationItems = [
    { to: "/chat", label: "Chat", icon: MessageCircle },
  ];

  return (
    <div className="app-mobile-drawer lg:hidden" role="dialog" aria-modal="true" aria-label="Workspace navigation" ref={drawerRef}>
      <button
        type="button"
        className="app-mobile-drawer__scrim"
        aria-label="Close navigation overlay"
        onClick={onClose}
      />
      <div className="app-mobile-drawer__panel">
        <div className="app-sidebar__top">
          <MobileLinkBrand appLabel={appLabel} />
          <button type="button" className="app-icon-button" aria-label="Close navigation" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>

        {user && (
          <div className="app-sidebar__account">
            <div className="account-avatar" aria-hidden="true">
              {user.email ? user.email.charAt(0).toUpperCase() : "U"}
            </div>
            <div className="account-info">
              <p title={user.email}>{user.email}</p>
              <span>{user.role}</span>
            </div>
          </div>
        )}

        <form className="app-sidebar__search" role="search" onSubmit={handleSearchSubmit}>
          <div className="app-sidebar__search-input-wrapper">
            <Search className="h-4 w-4 app-sidebar__search-icon" />
            <input
              type="text"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setSearchError("");
              }}
              placeholder="Search workspace"
              maxLength={80}
              className="app-sidebar__search-input"
              aria-label="Search workspace"
              aria-invalid={Boolean(searchError) || undefined}
            />
          </div>
          {searchError && <p className="app-sidebar__search-error">{searchError}</p>}
        </form>

        <div className="app-sidebar__scroll-area">
          <nav className="app-nav" aria-label="Workspace navigation">
            {navItems.map((item) => (
              <MobileSidebarNavItem key={item.to} item={item} onClose={onClose} />
            ))}
          </nav>
          <div className="app-sidebar__nav-label">Communication</div>
          <nav className="app-nav" aria-label="Communication">
            {communicationItems.map((item) => (
              <MobileSidebarNavItem key={item.to} item={item} onClose={onClose} />
            ))}
          </nav>
        </div>

        <div className="app-sidebar__bottom">
          <button
            type="button"
            onClick={handleLogout}
            className="app-sidebar__logout"
          >
            <LogOut className="h-5 w-5" aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
