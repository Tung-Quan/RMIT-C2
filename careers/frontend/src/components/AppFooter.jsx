import { BriefcaseBusiness, Mail, MapPin } from "lucide-react";
import { Link } from "react-router-dom";

export function AppFooter({ tone = "app" }) {
  const links =
    tone === "auth"
      ? [
          { to: "/", label: "Home" },
          { to: "/login", label: "Sign in" },
          { to: "/register", label: "Create account" }
        ]
      : [
          { to: "/candidate/jobs", label: "Jobs" },
          { to: "/candidate/profile", label: "Profile" },
          { to: "/applications", label: "Saved" }
        ];

  return (
    <footer className={`app-footer app-footer--${tone}`}>
      <div className="app-footer__brand">
        <span className="app-footer__mark" aria-hidden="true">
          <BriefcaseBusiness className="h-4 w-4" />
        </span>
        <div>
          <p>FairEnrol Careers</p>
          <span>Designed for confident career decisions.</span>
        </div>
      </div>

      <div className="app-footer__links" aria-label="Footer links">
        {links.map((link) => (
          <Link key={link.to} to={link.to}>{link.label}</Link>
        ))}
      </div>

      <div className="app-footer__meta">
        <span>
          <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
          Ho Chi Minh City
        </span>
        <span>
          <Mail className="h-3.5 w-3.5" aria-hidden="true" />
          Local development
        </span>
      </div>
    </footer>
  );
}
