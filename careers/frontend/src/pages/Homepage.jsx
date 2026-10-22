import {
  ArrowRight,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  FileText,
  GraduationCap,
  Link as LinkIcon,
  Menu,
  MousePointer2,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
  Phone,
  Headphones,
  MapPin,
  QrCode,
  Facebook,
  Youtube,
  Instagram,
  Search
} from "lucide-react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { LogoMarquee } from "../components/home/LogoMarquee";
import { parseWorkspaceSearch } from "../validation/forms";
import "./Homepage.css";

const images = {
  hero: {
    desktop: "/assets/home/hero/hero-career-workspace-desktop.webp",
    tablet: "/assets/home/hero/hero-career-workspace-tablet.webp",
    mobile: "/assets/home/hero/hero-career-workspace-mobile.webp",
    alt: "Diverse group of students collaborating around a laptop in a lecture hall."
  },
  opportunity: {
    desktop: "/assets/home/opportunities/opportunity-career-fair-desktop.webp",
    tablet: "/assets/home/opportunities/opportunity-career-fair-tablet.webp",
    mobile: "/assets/home/opportunities/opportunity-career-fair-mobile.webp",
    alt: "Students meeting employers at a university career fair."
  },
  final: {
    desktop: "/assets/home/final-cta/application-planning-desktop.webp",
    tablet: "/assets/home/final-cta/application-planning-tablet.webp",
    mobile: "/assets/home/final-cta/application-planning-mobile.webp",
    alt: "Student reviewing work on a laptop during application planning."
  }
};

const navItems = [
  { label: "Browse jobs", href: "#opportunities" },
  { label: "Career Paths", href: "#resources" },
  { label: "Companies", href: "#companies" },
  { label: "Resources", href: "#resources" }
];

const journeyNodes = [
  { label: "Candidate profile", icon: UserRound },
  { label: "Career match", icon: BriefcaseBusiness },
  { label: "Application submitted", icon: Send },
  { label: "Interview scheduled", icon: CalendarClock },
  { label: "Offer", icon: CheckCircle2 }
];

const narrativeSteps = [
  {
    number: "01",
    title: "Build a profile employers can understand",
    copy: "Collect academic context, contact details, portfolio proof, and a concise candidate story in one place before applications start moving.",
    visual: "profile"
  },
  {
    number: "02",
    title: "Find jobs that fit your direction",
    copy: "Browse roles by work mode, location, and employment type so every saved opportunity has a clear reason to be there.",
    visual: "opportunity"
  },
  {
    number: "03",
    title: "Track every application without losing momentum",
    copy: "Keep submissions, deadlines, interview dates, and next actions visible while the process changes week by week.",
    visual: "tracker"
  }
];

const milestones = [
  {
    label: "Profile ready",
    detail: "Your academic signal, links, and contact details are aligned.",
    metric: "82% ready"
  },
  {
    label: "Opportunity saved",
    detail: "A role is bookmarked with deadline and fit notes.",
    metric: "Remote hybrid"
  },
  {
    label: "Application submitted",
    detail: "Documents and application status move into the tracker.",
    metric: "Submitted"
  },
  {
    label: "Interview planned",
    detail: "The next conversation is scheduled with preparation cues.",
    metric: "Tue 10:30"
  },
  {
    label: "Decision recorded",
    detail: "The outcome is captured so the next move stays clear.",
    metric: "Offer"
  }
];

const profileSignals = [
  { label: "Academic context", value: "Ready", complete: true },
  { label: "Contact details", value: "Ready", complete: true },
  { label: "Portfolio links", value: "2/3", complete: true },
  { label: "Document readiness", value: "Missing CV", complete: false }
];

const opportunities = [
  {
    company: "Northstar Labs",
    role: "Product Design Intern",
    detail: "Hybrid - Ho Chi Minh City",
    deadline: "Deadline in 8 days"
  },
  {
    company: "Atlas Fintech",
    role: "Backend Engineering Intern",
    detail: "Remote - Part-time",
    deadline: "Interview slots open"
  },
  {
    company: "GreenGrid",
    role: "Data Analyst Intern",
    detail: "On-site - Summer program",
    deadline: "Save by Friday"
  }
];

const trackerStages = ["Saved", "Applied", "Interview", "Offer", "Rejected"];

function Reveal({ children, className = "", delay = 0, as = "div" }) {
  const shouldReduceMotion = useReducedMotion();
  const Component = motion[as];

  return (
    <Component
      className={className}
      initial={shouldReduceMotion ? false : { opacity: 0, y: 24 }}
      whileInView={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.58, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </Component>
  );
}

function PublicHeader() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState("opportunities");
  const closeButtonRef = useRef(null);

  useEffect(() => {
    function handleScroll() {
      setScrolled(window.scrollY > 20);
      const current = navItems
        .map((item) => item.href.slice(1))
        .findLast((id) => {
          const element = document.getElementById(id);
          return element && element.getBoundingClientRect().top < 180;
        });
      if (current) setActiveSection(current);
    }

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    if (menuOpen) closeButtonRef.current?.focus();

    function handleKeyDown(event) {
      if (event.key === "Escape") setMenuOpen(false);
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <header className={`homepage-header ${scrolled ? "homepage-header--scrolled" : ""}`}>
      <Link to="/" className="homepage-brand" aria-label="FairEnrol homepage">
        <span className="homepage-brand__mark" aria-hidden="true">
          <BriefcaseBusiness className="h-4 w-4" />
        </span>
        <span>FairEnrol</span>
      </Link>

      <div className="homepage-header__actions">
        <Link to="/login" className="homepage-link-button">
          Sign in
        </Link>
        <Link to="/register" className="homepage-button homepage-button--primary">
          Build my profile
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
        <button
          type="button"
          className="homepage-menu-button"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(true)}
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {menuOpen && (
        <div className="homepage-mobile-menu" role="dialog" aria-modal="true" aria-label="Mobile navigation">
          <button
            type="button"
            ref={closeButtonRef}
            className="homepage-menu-button homepage-mobile-menu__close"
            aria-label="Close menu"
            onClick={() => setMenuOpen(false)}
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
          <nav aria-label="Mobile primary navigation">
            {navItems.map((item) => (
              <a key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>
                {item.label}
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </a>
            ))}
          </nav>
          <div className="homepage-mobile-menu__actions">
            <Link to="/register" className="homepage-button homepage-button--primary" onClick={() => setMenuOpen(false)}>
              Build my profile
            </Link>
            <Link to="/login" className="homepage-button homepage-button--secondary" onClick={() => setMenuOpen(false)}>
              Sign in
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}

function HeroJourney() {
  const shouldReduceMotion = useReducedMotion();
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (shouldReduceMotion) return undefined;
    const interval = window.setInterval(() => {
      setActive((current) => (current + 1) % journeyNodes.length);
    }, 2600);
    return () => window.clearInterval(interval);
  }, [shouldReduceMotion]);

  return (
    <div className="hero-journey" aria-label="Career application journey">
      <div className="hero-journey__center">
        <div className="hero-journey__avatar">
          <GraduationCap className="h-7 w-7" aria-hidden="true" />
        </div>
        <p>Candidate identity</p>
        <span>Profile strength 82%</span>
      </div>
      <motion.div
        className="hero-journey__orbit"
        animate={shouldReduceMotion ? undefined : { rotate: 360 }}
        transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
        aria-hidden="true"
      >
        {journeyNodes.map((node, index) => {
          const Icon = node.icon;
          return (
            <button
              type="button"
              key={node.label}
              className={`hero-journey__node hero-journey__node--${index} ${active === index ? "is-active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              aria-label={node.label}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </button>
          );
        })}
      </motion.div>
      <svg className="hero-journey__path" viewBox="0 0 520 520" aria-hidden="true">
        <motion.circle
          cx="260"
          cy="260"
          r="188"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray="8 14"
          animate={shouldReduceMotion ? undefined : { pathLength: [0.25, 1, 0.25] }}
          transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        />
      </svg>
      <div className="hero-journey__caption">
        <span>{String(active + 1).padStart(2, "0")}</span>
        <p>{journeyNodes[active].label}</p>
      </div>
    </div>
  );
}

function ResponsiveImage({ image, className = "", loading = "lazy", sizes = "100vw" }) {
  return (
    <picture className={className}>
      <source media="(max-width: 640px)" srcSet={image.mobile} />
      <source media="(max-width: 1100px)" srcSet={image.tablet} />
      <img src={image.desktop} alt={image.alt} width="1400" height="934" loading={loading} sizes={sizes} />
    </picture>
  );
}

function HeroVisual() {
  return (
    <div className="hero-media">
      <ResponsiveImage image={images.hero} className="hero-media__photo" loading="eager" sizes="(max-width: 1100px) 100vw, 44vw" />
      <div className="hero-media__shade" aria-hidden="true" />
      <div className="hero-media__journey">
        <HeroJourney />
      </div>
      <div className="hero-media__caption">
        <span>Live workflow</span>
        <strong>Profile to interview</strong>
      </div>
    </div>
  );
}

function ProductVisual({ type }) {
  if (type === "profile") {
    return (
      <div className="product-visual product-visual--profile">
        <div className="readiness-ring" aria-hidden="true">
          <span>82%</span>
        </div>
        <div>
          <p className="product-visual__eyebrow">Candidate signal</p>
          <h3>Profile ready for review</h3>
          <dl>
            <div><dt>Academic context</dt><dd>Complete</dd></div>
            <div><dt>Portfolio</dt><dd>Connected</dd></div>
            <div><dt>Bio</dt><dd>Needs polish</dd></div>
          </dl>
        </div>
      </div>
    );
  }

  if (type === "opportunity") {
    return (
      <div className="product-visual product-visual--opportunity">
        <div className="stacked-preview stacked-preview--front">
          <p>Product Design Intern</p>
          <span>Hybrid - UX research - Due Friday</span>
        </div>
        <div className="stacked-preview stacked-preview--middle">
          <p>Data Analyst Intern</p>
          <span>Remote - SQL - Saved</span>
        </div>
        <div className="stacked-preview stacked-preview--back">
          <p>Backend Intern</p>
          <span>Part-time - API - Interviewing</span>
        </div>
      </div>
    );
  }

  return (
    <div className="product-visual product-visual--tracker">
      {trackerStages.slice(0, 4).map((stage, index) => (
        <div key={stage} className={index === 2 ? "is-current" : ""}>
          <span>{stage}</span>
          <strong>{index === 2 ? "Interview Tue" : index === 1 ? "2 active" : "1 item"}</strong>
        </div>
      ))}
    </div>
  );
}

function ProductNarrative() {
  return (
    <section className="homepage-section product-narrative" id="resources" aria-labelledby="value-title">
      <Reveal className="section-kicker">
        <p>Product value</p>
        <h2 id="value-title">One student workflow, from first profile draft to final decision.</h2>
      </Reveal>
      <div className="product-narrative__steps">
        {narrativeSteps.map((step, index) => (
          <Reveal
            key={step.number}
            as="article"
            className={`narrative-step ${index % 2 ? "narrative-step--reverse" : ""}`}
            delay={0.05}
          >
            <div className="narrative-step__copy">
              <span>{step.number}</span>
              <h3>{step.title}</h3>
              <p>{step.copy}</p>
            </div>
            <ProductVisual type={step.visual} />
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function ApplicationJourney() {
  const [active, setActive] = useState(0);
  const shouldReduceMotion = useReducedMotion();

  // Map the 5 steps to progress points along the path (0% to 100%)
  const progress = (active + 1) / milestones.length;

  return (
    <section className="homepage-section application-journey" aria-labelledby="journey-title">
      <Reveal className="application-journey__intro">
        <p className="homepage-eyebrow">Application journey</p>
        <h2 id="journey-title">The process stays visible even when the status changes.</h2>
      </Reveal>
      <div className="application-journey__grid">
        <div className="journey-timeline" role="list" aria-label="Application milestones">
          {milestones.map((milestone, index) => (
            <motion.button
              type="button"
              key={milestone.label}
              className={active === index ? "is-active" : ""}
              onClick={() => setActive(index)}
              onFocus={() => setActive(index)}
              onMouseEnter={() => setActive(index)}
              whileInView={() => setActive(index)}
              viewport={{ margin: "-45% 0px -45% 0px" }}
              role="listitem"
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{milestone.label}</strong>
              <small>{milestone.detail}</small>
            </motion.button>
          ))}
        </div>
        <Reveal className="journey-stage">
          <svg viewBox="0 0 460 280" aria-hidden="true" style={{ overflow: "visible" }}>
            {/* Background path (faint track) */}
            <path
              d="M28 210 C116 42 225 284 432 72"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              opacity={0.15}
            />
            {/* Active path */}
            <motion.path
              d="M28 210 C116 42 225 284 432 72"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              initial={shouldReduceMotion ? false : { pathLength: 0 }}
              animate={shouldReduceMotion ? undefined : { pathLength: progress }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            />
            {/* Moving dot */}
            {!shouldReduceMotion && (
              <motion.circle
                r="6"
                fill="currentColor"
                style={{
                  offsetPath: `path("M28 210 C116 42 225 284 432 72")`,
                }}
                initial={{ offsetDistance: "0%" }}
                animate={{ offsetDistance: `${progress * 100}%` }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              />
            )}
          </svg>
          <div className="journey-stage__note">
            <span>{milestones[active].metric}</span>
            <h3>{milestones[active].label}</h3>
            <p>{milestones[active].detail}</p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ProfileReadiness() {
  return (
    <section className="homepage-section readiness-preview" id="profile" aria-labelledby="profile-title">
      <Reveal className="readiness-preview__copy">
        <p className="homepage-eyebrow">Candidate profile</p>
        <h2 id="profile-title">Show the whole candidate, not scattered application fragments.</h2>
        <p>
          The profile preview turns academic details, contact channels, portfolio evidence, and document readiness into
          one reviewable signal.
        </p>
        <Link to="/candidate/profile" className="homepage-button homepage-button--primary">
          Build your candidate profile
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </Reveal>
      <Reveal className="readiness-orbit" delay={0.08}>
        <div className="readiness-orbit__identity">
          <span>CP</span>
          <strong>Candidate profile</strong>
          <small>82% ready</small>
        </div>
        {profileSignals.map((signal, index) => (
          <div key={signal.label} className={`readiness-orbit__point readiness-orbit__point--${index} ${signal.complete ? "" : "is-muted"}`}>
            <span>{signal.label}</span>
            <strong>{signal.value}</strong>
          </div>
        ))}
      </Reveal>
    </section>
  );
}

function CareerDiscovery() {
  const shouldReduceMotion = useReducedMotion();
  return (
    <section className="homepage-section opportunity-section" id="opportunities" aria-labelledby="opportunities-title">
      <Reveal className="opportunity-section__copy">
        <p className="homepage-eyebrow">Career opportunities</p>
        <h2 id="opportunities-title">Opportunities stay easy to compare without turning into a wall of job cards.</h2>
        <p>
          Use the existing job board when you are ready to browse live listings, filter by fit, and open the details that
          matter for your next application.
        </p>
        <Link to="/candidate/jobs" className="homepage-button homepage-button--secondary">
          Explore jobs
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </Reveal>
      <Reveal className="opportunity-showcase" delay={0.1}>
        <ResponsiveImage image={images.opportunity} className="opportunity-showcase__photo" sizes="(max-width: 1100px) 100vw, 62vw" />
        <div className="opportunity-showcase__annotation">
          <span>Career fair signal</span>
          <strong>Compare fit before you apply</strong>
        </div>
        <div className="opportunity-rail" aria-label="Opportunity examples" style={{ overflowX: "hidden" }}>
          <motion.div
            style={{ display: "flex", gap: "1rem", width: "max-content", paddingRight: "1rem" }}
            animate={shouldReduceMotion ? undefined : { x: ["0%", "-50%"] }}
            transition={{ duration: 25, ease: "linear", repeat: Infinity }}
          >
            {[...opportunities, ...opportunities].map((opportunity, index) => (
              <motion.article
                key={`${opportunity.company}-${index}`}
                className={index % 3 === 1 ? "is-focused" : ""}
                whileHover={{ y: -6 }}
                transition={{ duration: 0.18 }}
              >
                <span>{opportunity.company}</span>
                <h3>{opportunity.role}</h3>
                <p>{opportunity.detail}</p>
                <small>{opportunity.deadline}</small>
              </motion.article>
            ))}
          </motion.div>
        </div>
      </Reveal>
    </section>
  );
}

function TrackerPreview() {
  return (
    <section className="homepage-section tracker-preview" id="tracker" aria-labelledby="tracker-title">
      <Reveal className="tracker-preview__visual">
        <div className="tracker-lane" aria-label="Application tracker preview">
          {trackerStages.map((stage, index) => (
            <div key={stage} className={stage === "Interview" ? "is-active" : ""}>
              <span>{stage}</span>
              {stage === "Interview" && (
                <motion.strong layoutId="application-chip">
                  <MousePointer2 className="h-4 w-4" aria-hidden="true" />
                  UX Intern - Tue 10:30
                </motion.strong>
              )}
            </div>
          ))}
        </div>
      </Reveal>
      <Reveal className="tracker-preview__copy" delay={0.08}>
        <p className="homepage-eyebrow">Application tracker</p>
        <h2 id="tracker-title">See status, deadline, and next action in the same motion.</h2>
        <p>
          Saved roles, submitted applications, interviews, decisions, and rejected outcomes stay separated without
          becoming a heavy dashboard.
        </p>
        <Link to="/candidate/job-applications" className="homepage-button homepage-button--primary">
          Track applications
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </Reveal>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="final-cta" aria-labelledby="final-cta-title">
      <ResponsiveImage image={images.final} className="final-cta__image" loading="lazy" sizes="100vw" />
      <div className="final-cta__overlay" aria-hidden="true" />
      <Reveal className="final-cta__content">
        <p className="homepage-eyebrow">Ready when you are</p>
        <h2 id="final-cta-title">Start building your career journey.</h2>
        <div className="final-cta__actions">
          <Link to="/register" className="homepage-button homepage-button--primary">
            Create candidate profile
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link to="/candidate/jobs" className="homepage-button homepage-button--ghost">
            Explore jobs
          </Link>
        </div>
      </Reveal>
    </section>
  );
}

export function Homepage() {
  const [showBranches, setShowBranches] = useState(false);
  const [heroSearch, setHeroSearch] = useState("");
  const [heroSearchError, setHeroSearchError] = useState("");
  const shouldReduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuth();

  if (isAuthenticated) {
    const dashboardPath = user?.role === "hr" ? "/hr/dashboard" : "/candidate/dashboard";
    return <Navigate to={dashboardPath} replace />;
  }

  function handleHeroSearch(event) {
    event.preventDefault();
    const parsed = parseWorkspaceSearch(heroSearch);
    if (parsed.error) {
      setHeroSearchError(parsed.error);
      return;
    }
    setHeroSearchError("");
    const params = new URLSearchParams();
    if (parsed.query) params.set("keyword", parsed.query);
    navigate(`/candidate/jobs${params.toString() ? `?${params.toString()}` : ""}`);
  }

  return (
    <div className="homepage">
      <PublicHeader />
      <main>
        <section className="homepage-hero" aria-labelledby="homepage-title">
          <Reveal className="homepage-hero__copy">
            <p className="homepage-eyebrow">Career opportunities for students</p>
            <h1 id="homepage-title">Your first opportunity should feel like the right one.</h1>
            <p>
              Discover roles matched to your skills, apply with confidence, and track every step in one place.
            </p>
            <form className="homepage-search" onSubmit={handleHeroSearch} role="search" aria-label="Search jobs">
              <label htmlFor="homepage-career-search">Search jobs</label>
              <div className="homepage-search__control">
                <Search className="h-5 w-5" aria-hidden="true" />
                <input
                  id="homepage-career-search"
                  value={heroSearch}
                  onChange={(event) => {
                    setHeroSearch(event.target.value);
                    setHeroSearchError("");
                  }}
                  placeholder="Try product design, data, backend..."
                  maxLength={80}
                  aria-invalid={Boolean(heroSearchError) || undefined}
                />
                <button type="submit">Search</button>
              </div>
              {heroSearchError && <p className="homepage-search__error">{heroSearchError}</p>}
            </form>
            <div className="homepage-hero__actions">
              <Link to="/register" className="homepage-button homepage-button--primary">
                Create candidate profile
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link to="/candidate/jobs" className="homepage-button homepage-button--secondary">
                Explore jobs
              </Link>
            </div>
            <div className="homepage-hero__trust">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              <span>Profile, opportunity discovery, documents, interviews, and deadlines in one student workflow.</span>
            </div>
          </Reveal>
          <Reveal className="homepage-hero__visual" delay={0.08}>
            <HeroVisual />
            <motion.div
              className="homepage-floating-card homepage-floating-card--match"
              animate={shouldReduceMotion ? undefined : { y: [0, -5, 0] }}
              transition={{ duration: 5.2, repeat: Infinity, ease: "easeInOut" }}
            >
              <span>Job Match</span>
              <strong>84%</strong>
              <small>Product Design Intern</small>
            </motion.div>
            <motion.div
              className="homepage-floating-card homepage-floating-card--interview"
              animate={shouldReduceMotion ? undefined : { y: [0, 4, 0] }}
              transition={{ duration: 5.8, repeat: Infinity, ease: "easeInOut" }}
            >
              <span>Interview scheduled</span>
              <strong>Tue 10:30</strong>
              <small>Northstar Labs</small>
            </motion.div>
          </Reveal>
        </section>
        <LogoMarquee />
        <ProductNarrative />
        <ApplicationJourney />
        <ProfileReadiness />
        <CareerDiscovery />
        <TrackerPreview />
        <FinalCta />
      </main>
      <footer className="homepage-footer">
        <div className="homepage-footer__top">
          <div className="homepage-footer__brand">
            <Link to="/" className="homepage-brand">
              <div className="homepage-brand__text">
                <strong>FairEnrol</strong>
                <span>by Team:</span>
              </div>
            </Link>
          </div>
          <div className="homepage-footer__contacts">
            <div className="footer-contact">
              <Phone className="h-8 w-8" aria-hidden="true" />
              <div>
                <span>Hotline</span>
                <strong>1900 1881</strong>
              </div>
            </div>
            <div className="footer-contact">
              <UserRound className="h-8 w-8" aria-hidden="true" />
              <div>
                <span>Customer Support</span>
                <strong>support@fairenrol.example</strong>
              </div>
            </div>
            <div className="footer-contact">
              <Headphones className="h-8 w-8" aria-hidden="true" />
              <div>
                <span>Customer Care</span>
                <strong>care@fairenrol.example</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="homepage-footer__main">
          <div className="footer-column footer-company">
            <h4>FAIRENROL</h4>
            <p>
              <MapPin className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <span>Floor 31, Keangnam Hanoi Landmark Tower, Yen Hoa Ward, Hanoi, Vietnam</span>
            </p>
            <p>
              <Phone className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <span>(024) 3562 5939 - (024) 3562 5940</span>
            </p>
            <div className="footer-apps">
              <QrCode className="h-16 w-16" aria-hidden="true" />
              <div className="footer-apps__links">
                <button type="button" className="footer-app-btn">
                  <span className="font-bold">Google Play</span>
                </button>
                <button type="button" className="footer-app-btn">
                  <span className="font-bold">App Store</span>
                </button>
              </div>
            </div>
          </div>
          <div className="footer-column">
            <h4>GUIDES</h4>
            <Link to="#">About Us</Link>
            <Link to="#">Pricing & Support</Link>
            <Link to="#">FAQ</Link>
            <Link to="#">Report a Bug</Link>
            <Link to="#">Sitemap</Link>
          </div>
          <div className="footer-column">
            <h4>REGULATIONS</h4>
            <Link to="#">Posting Rules</Link>
            <Link to="#">Operating Regulations</Link>
            <Link to="#">Terms of Agreement</Link>
            <Link to="#">Privacy Policy</Link>
            <Link to="#">Complaint Resolution</Link>
          </div>
          <div className="footer-column footer-newsletter">
            <h4>SUBSCRIBE TO NEWSLETTER</h4>
            <div className="newsletter-input">
              <input id="homepage-newsletter-email" name="newsletterEmail" type="email" placeholder="Enter your email" />
              <button type="button" aria-label="Subscribe">
                <Send className="h-4 w-4" />
              </button>
            </div>
            <h4 className="footer-newsletter__second-heading">COUNTRY & LANGUAGE</h4>
            <div className="footer-language-select">
              <select id="homepage-country-language" name="countryLanguage" aria-label="Select country and language">
                <option>Vietnam</option>
                <option>English</option>
              </select>
            </div>
          </div>
        </div>

        <div className="homepage-footer__branches">
          <button type="button" className="branches-toggle" onClick={() => setShowBranches(!showBranches)}>
            <ChevronRight className={`h-4 w-4 transition-transform ${showBranches ? 'rotate-90' : ''}`} /> View FairEnrol branches
          </button>
          {showBranches && (
            <div className="footer-branches-grid">
              <div className="branch-item">
                <h5>Ho Chi Minh City Branch</h5>
                <p>Floor 26, Bitexco financial tower, 2,Hai Trieu Street, Sai Gon District, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
              <div className="branch-item">
                <h5>Hai Phong Branch</h5>
                <p>Room 502, Floor 5, TD Business Center Building, Lot 20A, Le Hong Phong Street, Ngo Quyen District, Hai Phong City, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
              <div className="branch-item">
                <h5>Binh Duong Branch</h5>
                <p>Floor 5, Biconsi Tower, No. 1 Phu Loi Street, Phu Loi Ward, Thu Dau Mot City, Binh Duong Province, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
              <div className="branch-item">
                <h5>Da Nang Branch</h5>
                <p>Floor 9, Vinh Trung Plaza, 255-257 Hung Vuong, Thanh Khe District, Da Nang City, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
              <div className="branch-item">
                <h5>Vung Tau Branch</h5>
                <p>Floor 4, ACB Building, 111 Hoang Hoa Tham, Thang Tam Ward, Vung Tau City, Ba Ria - Vung Tau Province, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
              <div className="branch-item">
                <h5>Nha Trang Branch</h5>
                <p>11 Ly Thanh Ton, Van Thanh Ward, Nha Trang City, Khanh Hoa Province, Vietnam</p>
                <p>Hotline: 1900 1881</p>
              </div>
            </div>
          )}
        </div>

        <div className="homepage-footer__bottom">
          <div className="footer-copyright">
            <p>Copyright (c) 2024 - 2026 FairEnrol</p>
            <p>Business Registration Certificate No. 0104630479 issued by Hanoi DPI on June 02, 2010</p>
            <p>Legal Representative: Tuan</p>
          </div>
          <div className="footer-legal">
            <p>Responsible for E-commerce: Tuan</p>
            <p>Transaction regulations effective from Aug 08, 2026</p>
            <p>Clearly state the source "FairEnrol" when republishing information from this website.</p>
          </div>
          <div className="footer-socials">
            <div className="footer-certificate">
              <ShieldCheck className="h-10 w-10 text-red-600" aria-label="Registered with MOIT" />
              <span className="text-[10px] font-bold text-red-600 leading-tight">REGISTERED<br/>WITH MOIT</span>
            </div>
            <div className="social-icons">
              <button type="button" aria-label="Facebook"><Facebook className="h-5 w-5" /></button>
              <button type="button" aria-label="Youtube"><Youtube className="h-5 w-5" /></button>
              <button type="button" aria-label="Instagram"><Instagram className="h-5 w-5" /></button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
