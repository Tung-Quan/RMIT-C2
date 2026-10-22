import {
  BriefcaseBusiness,
  Building2,
  FileSearch,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Menu,
  PlusCircle,
  Send,
  UserRound,
  Bookmark
} from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { AppFooter } from "./AppFooter";
import { useAuth } from "../context/AuthContext";
import { AppSidebar } from "./AppSidebar";
import { MobileSidebarDrawer } from "./MobileSidebarDrawer";

const candidateNavItems = [
  { to: "/candidate/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/candidate/jobs", label: "Job Board", icon: BriefcaseBusiness },
  { to: "/candidate/job-applications", label: "Submissions", icon: Send },
  { to: "/applications", label: "Saved", icon: Bookmark },
  { to: "/applications/ai-cv-matching", label: "AI CV Matching", icon: FileSearch },
  { to: "/candidate/profile", label: "Profile", icon: UserRound }
];

const hrNavItems = [
  { to: "/hr/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/hr/company", label: "Company", icon: Building2 },
  { to: "/hr/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { to: "/hr/jobs/new", label: "New Job", icon: PlusCircle }
];

const candidateMobileItems = [
  { to: "/candidate/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/candidate/jobs", label: "Explore", icon: BriefcaseBusiness },
  { to: "/candidate/job-applications", label: "Applications", icon: Send },
  { to: "/candidate/profile", label: "Profile", icon: UserRound },
];

const hrMobileItems = [
  { to: "/hr/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/hr/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { to: "/chat", label: "Chat", icon: MessageCircle },
  { to: "/hr/company", label: "Company", icon: Building2 },
];

function MobileBottomTabs({ items, location }) {
  return (
    <nav className="careers-mobile-tabs" aria-label="FairEnrol Careers navigation">
      {items.map((item) => {
        const active = location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
        return (
          <NavLink key={item.to} to={item.to} end={item.to === "/candidate/dashboard" || item.to === "/hr/dashboard"} className={`careers-mobile-tab${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined}>
            <item.icon className="h-5 w-5" aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}

function LinkBrand({ appLabel }) {
  return (
    <div className="app-brand">
      <span className="app-brand__mark" aria-hidden="true">
        <BriefcaseBusiness className="h-4 w-4" />
      </span>
      <div className="app-brand__text">
        <p>{appLabel}</p>
        <span>Workspace</span>
      </div>
    </div>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const isCandidateWorkspace = user?.role !== "hr" || location.pathname.startsWith("/candidate") || location.pathname.startsWith("/applications");
  const navItems = isCandidateWorkspace ? candidateNavItems : hrNavItems;
  const appLabel = isCandidateWorkspace ? "FairEnrol Careers" : "FairEnrol Hiring";
  const isChatRoute = location.pathname === "/chat";

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = isMobileNavOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isMobileNavOpen]);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className={`app-shell ${isCandidateWorkspace ? "app-shell--candidate" : "app-shell--hr"}`}>
      <AppSidebar
        user={user}
        navItems={navItems}
        appLabel={appLabel}
        logout={logout}
      />

      <header className="app-mobile-bar lg:hidden">
        <button
          type="button"
          onClick={() => setIsMobileNavOpen(true)}
          className="app-icon-button"
          aria-label="Open navigation"
          aria-expanded={isMobileNavOpen}
        >
          <Menu className="h-4 w-4" />
        </button>
        <LinkBrand appLabel={appLabel} />
        <button type="button" onClick={handleLogout} className="app-icon-button" aria-label="Sign out">
          <LogOut className="h-4 w-4" />
        </button>
      </header>

      <MobileSidebarDrawer
        isOpen={isMobileNavOpen}
        onClose={() => setIsMobileNavOpen(false)}
        user={user}
        navItems={navItems}
        appLabel={appLabel}
        logout={logout}
      />

      <div className={`app-content ${isChatRoute ? "app-content--flush" : "lg:has-collapsed-sidebar:pl-[5.5rem] lg:has-expanded-sidebar:pl-72"}`}>
        <main className={isChatRoute ? "h-[calc(100dvh-3.5rem)] w-full overflow-hidden p-0 lg:h-dvh" : "mx-auto w-full max-w-7xl overflow-x-hidden px-4 py-5 pb-28 sm:px-6 lg:px-8 lg:py-7 lg:pb-7"}>
          <div key={location.pathname} className={isChatRoute ? "route-panel h-full min-h-0" : "route-panel"}>
            <Outlet />
          </div>
        </main>
        {!isChatRoute && (
          <div className="mx-auto w-full max-w-7xl px-4 pb-6 sm:px-6 lg:px-8">
            <AppFooter tone={isCandidateWorkspace ? "candidate" : "app"} />
          </div>
        )}
      </div>
      {!isChatRoute && <MobileBottomTabs items={isCandidateWorkspace ? candidateMobileItems : hrMobileItems} location={location} />}
    </div>
  );
}
