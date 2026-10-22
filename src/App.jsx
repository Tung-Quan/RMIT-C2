import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTideCloak } from "@tidecloak/react";
import { createApi } from "./api/client.js";

const actionNames = {
  force: "Force enrol",
  jump: "Move to front of queue",
  remove: "Remove a student",
  panel: "Change approver panel",
};
function Brand() {
  return (
    <a className="brand" href="/">
      <span className="brand-mark">F</span> FairEnrol
    </a>
  );
}
function Footer() {
  return (
    <footer>
      <span>FairEnrol · A fair place in every queue.</span>
      <span>Identity by TideCloak · Enrolment rules enforced by FairEnrol</span>
    </footer>
  );
}
function TabIcon({ name }) {
  const paths = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>,
    review: <><path d="M9 11 12 14 20 6" /><path d="M20 12v7H4V5h11" /></>,
    careers: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></>,
    profile: <><circle cx="12" cy="8" r="4" /><path d="M5 21a7 7 0 0 1 14 0" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
function MobileBottomNavigation({ authenticated, isLoading, user, view, setView, login, logout, onAuthError }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const roles = user?.roles || [];
  const homeRole = roles.includes("student") ? "student" : roles[0];
  const reviewRole = roles.includes("approver") ? "approver" : roles.includes("registrar") ? "registrar" : null;
  const signIn = () => login().catch(onAuthError);

  return (
    <>
      {profileOpen && (
        <div className="mobile-profile-scrim" onClick={() => setProfileOpen(false)}>
          <section id="mobile-profile-sheet" className="mobile-profile-sheet" role="dialog" aria-modal="true" aria-label="Your FairEnrol account" onClick={(event) => event.stopPropagation()}>
            <div className="mobile-profile-heading">
              <span className="eyebrow">YOUR ACCOUNT</span>
              <button type="button" aria-label="Close account panel" onClick={() => setProfileOpen(false)}>×</button>
            </div>
            <strong>{user?.name || "Welcome to FairEnrol"}</strong>
            <p>{user ? `${user.title} · ${roles.join(" · ")}` : "Sign in to view your courses and account."}</p>
            <button className="button dark" disabled={isLoading} onClick={() => (authenticated ? logout() : signIn())}>
              {authenticated ? "Sign out" : "Sign in with TideCloak"}
            </button>
          </section>
        </div>
      )}
      <nav className="mobile-bottom-nav" aria-label="FairEnrol navigation">
        <button type="button" className={`mobile-bottom-link ${!profileOpen && (view === homeRole || !authenticated) ? "active" : ""}`} onClick={() => { if (homeRole) setView(homeRole); setProfileOpen(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          <TabIcon name="home" /><span>Home</span>
        </button>
        {reviewRole && (
          <button type="button" className={`mobile-bottom-link ${view === reviewRole ? "active" : ""}`} onClick={() => { setView(reviewRole); setProfileOpen(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
            <TabIcon name="review" /><span>Review</span>
          </button>
        )}
        <a className="mobile-bottom-link" href="/careers/index.html">
          <TabIcon name="careers" /><span>Careers</span>
        </a>
        <button type="button" className={`mobile-bottom-link ${profileOpen ? "active" : ""}`} aria-expanded={profileOpen} aria-controls="mobile-profile-sheet" onClick={() => setProfileOpen((open) => !open)}>
          <TabIcon name="profile" /><span>Account</span>
        </button>
      </nav>
    </>
  );
}
function Avatar({ person, index = 0 }) {
  return (
    <span title={person.name} className={`avatar a${index % 3}`}>
      {person.name
        .split(" ")
        .map((p) => p[0])
        .slice(-2)
        .join("")}
    </span>
  );
}
function Hero({ panel = [] }) {
  return (
    <section className="hero">
      <div>
        <div className="eyebrow">
          <span /> COURSE REGISTRATION, WITHOUT FAVOURS
        </div>
        <h1>
          A fair place
          <br />
          in every queue.
        </h1>
        <p>
          First come, first served. Exceptions need a clear reason and two
          independent approvals.
        </p>
      </div>
      <div className="hero-card">
        <span className="card-kicker">COLLECTIVE REVIEW</span>
        <strong>
          Every exception.
          <br />
          Two independent voices.
        </strong>
        <div className="avatar-stack">
          {panel.map((p, i) => (
            <Avatar key={p.id} person={p} index={i} />
          ))}
        </div>
        <small>Three panel members · two approvals required</small>
      </div>
    </section>
  );
}
function SectionTitle({ eyebrow, title, detail }) {
  return (
    <div className="section-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
      </div>
      {detail && <span className="count-pill">{detail}</span>}
    </div>
  );
}
export function SetupScreen({ message, retry }) {
  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        <span className="auth-state">Local development</span>
      </header>
      <Hero />
      <section className="welcome-card">
        <div className="eyebrow">CONNECT YOUR CAMPUS</div>
        <h2>Finish connecting TideCloak</h2>
        <p>
          {message ||
            "The identity service is being configured. Course actions will be available after a secure sign-in."}
        </p>
        <ol>
          <li>
            Start the local services with <code>docker compose up -d</code>.
          </li>
          <li>
            Run <code>npm run tide:setup</code> and complete the Tide
            account-linking step.
          </li>
          <li>
            Run <code>npm run dev</code> and return here.
          </li>
        </ol>
        <button
          className="button dark"
          onClick={retry || (() => location.reload())}
        >
          Check connection again
        </button>
      </section>
      <Footer />
    </main>
  );
}
export default function App() {
  const {
    authenticated,
    isInitializing,
    isLoading,
    initError,
    login,
    logout,
    secureFetch,
    reload,
  } = useTideCloak();
  // Standard frontchannel callbacks are processed by the provider's IAMService initialization.
  // useAuthCallback is for hybrid mode and would race that token exchange here.
  useEffect(() => {
    if (
      !isInitializing &&
      authenticated &&
      location.pathname === "/auth/redirect"
    )
      history.replaceState(null, "", "/");
    if (!isInitializing && authenticated && sessionStorage.getItem("fairenrol:postLogin") === "/careers/index.html") {
      sessionStorage.removeItem("fairenrol:postLogin");
      location.replace("/careers/index.html");
    }
  }, [authenticated, isInitializing]);
  const fetchRef = useRef(secureFetch);
  fetchRef.current = secureFetch;
  const api = useMemo(
    () => createApi((...args) => fetchRef.current(...args)),
    [],
  );
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState("student");
  const refresh = useCallback(
    async (signal) => {
      const next = await api("/api/state", { signal });
      setState(next);
      setError("");
    },
    [api],
  );
  useEffect(() => {
    if (!authenticated || isInitializing) {
      setState(null);
      return;
    }
    const controller = new AbortController();
    const poll = () => {
      if (!document.hidden)
        refresh(controller.signal).catch((e) => {
          if (!controller.signal.aborted) {
            setError(e.message);
            if (e.status === 401 || e.status === 403) setState(null);
          }
        });
    };
    poll();
    const timer = setInterval(poll, 15000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [authenticated, isInitializing, refresh]);
  useEffect(() => {
    if (state && !state.user.roles.includes(view)) setView(state.user.roles[0]);
  }, [state, view]);
  async function run(path, method, body = {}) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api(path, { method, body });
      setNotice(result.message);
      await refresh();
    } catch (e) {
      setError(e.message);
      if (e.status === 401 || e.status === 403) setState(null);
    } finally {
      setBusy(false);
    }
  }
  if (isInitializing)
    return (
      <main className="loading" role="status">
        Connecting to TideCloak…
      </main>
    );
  const user = state?.user;
  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        <div className="top-actions">
          <a className="button light" href="/careers/index.html">Careers ↗</a>
          <span className={`auth-state ${authenticated ? "connected" : ""}`}>
            <i />
            {user?.name ||
              (authenticated
                ? "TideCloak · signed in"
                : "TideCloak · secure sign-in")}
          </span>
          <button
            className="button dark"
            disabled={isLoading}
            onClick={() =>
              (authenticated ? logout() : login()).catch((e) =>
                setError(e.message),
              )
            }
          >
            {authenticated ? "Log out" : "Log in with TideCloak"}
          </button>
        </div>
      </header>
      <Hero panel={state?.panel} />
      {(error || initError) && (
        <div className="notice login-error" role="alert">
          {error || initError.message}
          <button
            className="button quiet"
            onClick={() =>
              initError ? reload() : refresh().catch((e) => setError(e.message))
            }
          >
            Retry
          </button>
        </div>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            ×
          </button>
        </div>
      )}
      {!authenticated ? (
        <section className="welcome-card">
          <div className="eyebrow">YOUR PLACE STARTS HERE</div>
          <h2>One identity. A shared, fair queue.</h2>
          <p>
            Sign in to see your courses and waitlist positions. Registrars and
            reviewers get the tools assigned to their accounts.
          </p>
          <button
            className="button dark"
            disabled={isLoading || !!initError}
            onClick={() => login().catch((e) => setError(e.message))}
          >
            Continue with TideCloak <span aria-hidden="true">→</span>
          </button>
        </section>
      ) : !state ? (
        <section className="welcome-card" role="status">
          <h2>
            {error ? "Your account needs attention" : "Loading your campus…"}
          </h2>
          <p>{error || "Reading your identity and course records."}</p>
        </section>
      ) : (
        <>
          <nav className="toolbar" aria-label="Your workspaces">
            <div>
              <span className="workspace-label">YOUR WORKSPACE</span>
              {user.roles.map((role) => (
                <button
                  key={role}
                  className={`workspace-tab ${view === role ? "active" : ""}`}
                  aria-pressed={view === role}
                  onClick={() => setView(role)}
                >
                  {role === "student"
                    ? "My courses"
                    : role === "registrar"
                      ? "Course administration"
                      : "Exception review"}
                </button>
              ))}
            </div>
            <div className="role-hint">
              {user.title} · Shared records refresh every 15 seconds
            </div>
          </nav>
          {view === "student" && (
            <section className="section">
              <SectionTitle
                eyebrow="STUDENT DASHBOARD"
                title="Your courses"
                detail={`${state.courses.length} courses`}
              />
              <div className="course-grid">
                {state.courses.map((course) => (
                  <article className="course-card" key={course.id}>
                    <div className="course-top">
                      <span className="course-code">{course.code}</span>
                      <span
                        className={`seats ${course.enrolledCount < course.capacity ? "open" : "full"}`}
                      >
                        {Math.max(0, course.capacity - course.enrolledCount)}{" "}
                        seats open
                      </span>
                    </div>
                    <h3>{course.name}</h3>
                    <CourseStats course={course} />
                    {course.myStatus ? (
                      <>
                        <div
                          className={`queue-status ${course.myStatus === "enrolled" ? "enrolled" : ""}`}
                        >
                          {course.myStatus === "enrolled"
                            ? "Your place is confirmed"
                            : `You are #${course.myPosition} on the waitlist`}
                          <small>
                            {course.myStatus === "enrolled"
                              ? "You are enrolled in this course."
                              : "Places are offered in FIFO order."}
                          </small>
                        </div>
                        <button
                          className="button quiet full-width"
                          disabled={busy}
                          onClick={() =>
                            run(
                              `/api/courses/${course.id}/enrolments/me`,
                              "DELETE",
                            )
                          }
                        >
                          Withdraw
                        </button>
                      </>
                    ) : (
                      <button
                        className="button dark full-width"
                        disabled={busy}
                        onClick={() =>
                          run(`/api/courses/${course.id}/enrolments`, "POST")
                        }
                      >
                        {course.enrolledCount < course.capacity
                          ? "Enrol in course"
                          : "Join waitlist"}
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )}
          {view === "registrar" && (
            <section className="section">
              <SectionTitle
                eyebrow="REGISTRAR DASHBOARD"
                title="Course administration"
                detail="Capacity and exception requests"
              />
              <div className="registrar-grid">
                {state.courses.map((course) => (
                  <article className="course-card" key={course.id}>
                    <span className="course-code">{course.code}</span>
                    <h3>{course.name}</h3>
                    <CapacityEditor
                      course={course}
                      busy={busy}
                      save={(capacity) =>
                        run(`/api/courses/${course.id}/capacity`, "PATCH", {
                          capacity,
                        })
                      }
                    />
                    <CourseStats course={course} />
                  </article>
                ))}
              </div>
              <div className="policy-note">
                Queue order, forced enrolment, student removal and panel changes
                require an exception with two independent approvals.
              </div>
              <RequestForm
                state={state}
                busy={busy}
                submit={(body) => run("/api/exception-requests", "POST", body)}
              />
            </section>
          )}
          {view === "approver" && (
            <section className="section">
              <SectionTitle
                eyebrow="APPROVER PANEL"
                title="Independent exception review"
                detail="Two of three required"
              />
              <div className="panel-strip">
                {state.panel.map((person, i) => (
                  <div className="panel-person" key={person.id}>
                    <Avatar person={person} index={i} />
                    <span>
                      <strong>{person.name}</strong>
                      <small>{person.title}</small>
                    </span>
                  </div>
                ))}
              </div>
              <RequestForm
                state={state}
                busy={busy}
                submit={(body) => run("/api/exception-requests", "POST", body)}
              />
            </section>
          )}
          {view !== "student" && (
            <section className="section">
              <SectionTitle
                eyebrow="REVIEW HISTORY"
                title="Exception requests"
                detail={`${state.requests.filter((r) => r.status === "pending").length} pending`}
              />
              <div className="request-list">
                {state.requests.map((request) => (
                  <RequestCard
                    key={request.id}
                    {...{ request, state, user, busy, run }}
                  />
                ))}
                {!state.requests.length && (
                  <p className="empty">No exception requests yet.</p>
                )}
              </div>
            </section>
          )}
          <section className="section">
            <SectionTitle
              eyebrow="PUBLIC EXCEPTIONS"
              title="Reasons that changed a queue"
            />
            <div className="reason-list">
              {state.publicExceptions.map((request) => (
                <div className="reason-item" key={request.id}>
                  <span className="approved-tag">APPROVED</span>
                  <div>
                    <strong>{actionNames[request.kind]}</strong>
                    <p>{request.reason}</p>
                  </div>
                </div>
              ))}
              {!state.publicExceptions.length && (
                <p className="empty">No exceptions have been approved.</p>
              )}
            </div>
          </section>
          <section className="section audit-section">
            <SectionTitle
              eyebrow="SHARED HISTORY"
              title="Activity log"
              detail="Recorded by the server"
            />
            <div className="audit-list">
              {state.audit.map((entry) => (
                <div className="audit-row" key={entry.id}>
                  <time dateTime={entry.time}>
                    {new Date(entry.time).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                  <span className="audit-dot" />
                  <div>
                    <strong>{entry.kind.split(".").join(" ")}</strong>
                    <p>{entry.summary}</p>
                  </div>
                </div>
              ))}
              {!state.audit.length && (
                <p className="empty">
                  Course actions and approval decisions will appear here.
                </p>
              )}
            </div>
          </section>
        </>
      )}
      <MobileBottomNavigation authenticated={authenticated} isLoading={isLoading} user={user} view={view} setView={setView} login={login} logout={logout} onAuthError={(e) => setError(e.message)} />
      <Footer />
    </main>
  );
}
function RequestCard({ request, state, user, busy, run }) {
  const course = state.courses.find((c) => c.id === request.data.courseId);
  const target = state.people.find((p) => p.id === request.data.studentId);
  const canVote =
    user.roles.includes("approver") &&
    state.panel.some((p) => p.id === user.id) &&
    request.panelSnapshot.includes(user.id) &&
    request.requesterId !== user.id &&
    !request.approvals.some((p) => p.id === user.id);
  return (
    <article className="request-card">
      <div className="request-head">
        <div>
          <span className="eyebrow">{actionNames[request.kind]}</span>
          <h3>
            {request.kind === "panel"
              ? `Replace ${state.people.find((p) => p.id === request.data.replaceId)?.name} with ${state.people.find((p) => p.id === request.data.candidateId)?.name}`
              : `${target?.name || "Student"} · ${course?.code}`}
          </h3>
        </div>
        <span className={`status-tag ${request.status}`}>{request.status}</span>
      </div>
      <p className="request-reason">Reviewer details: {request.reason}</p>
      <p className="request-reason">
        Public explanation: {request.publicReason}
      </p>
      {request.kind === "force" && (
        <p className="request-reason">
          Approved capacity would be {request.data.resultingCapacity}.
        </p>
      )}
      <div className="vote-row">
        <span>
          {request.approvals.length} of 2 approvals · Requested by{" "}
          {request.requester}
        </span>
        {request.approvals.map((person) => (
          <Avatar key={person.id} person={person} />
        ))}
      </div>
      {request.status === "pending" && (
        <div className="request-actions">
          {canVote ? (
            <>
              <button
                className="button approve"
                disabled={busy}
                onClick={() =>
                  run(`/api/exception-requests/${request.id}/approvals`, "POST")
                }
              >
                Approve as yourself
              </button>
              <button
                className="button text-button"
                disabled={busy}
                onClick={() =>
                  run(`/api/exception-requests/${request.id}/denial`, "POST")
                }
              >
                Deny request
              </button>
            </>
          ) : (
            <span className="muted">
              {request.requesterId === user.id
                ? "Your request needs independent reviewers."
                : request.approvals.some((p) => p.id === user.id)
                  ? "Your approval is recorded."
                  : "Only eligible panel members may review this request."}
            </span>
          )}
        </div>
      )}
    </article>
  );
}
function CourseStats({ course }) {
  return (
    <div className="course-stats">
      <span>
        Enrolled{" "}
        <b>
          {course.enrolledCount}/{course.capacity}
        </b>
      </span>
      <span>
        Waiting <b>{course.waitingCount}</b>
      </span>
    </div>
  );
}
function CapacityEditor({ course, busy, save }) {
  const [capacity, setCapacity] = useState(String(course.capacity));
  useEffect(() => setCapacity(String(course.capacity)), [course.capacity]);
  return (
    <form
      className="capacity-label"
      onSubmit={(event) => {
        event.preventDefault();
        save(Number(capacity));
      }}
    >
      <label htmlFor={`capacity-${course.id}`}>Seat limit</label>
      <input
        id={`capacity-${course.id}`}
        type="number"
        min={Math.max(1, course.enrolledCount)}
        max="10000"
        required
        value={capacity}
        onChange={(e) => setCapacity(e.target.value)}
      />
      <button className="button quiet" disabled={busy}>
        Save
      </button>
    </form>
  );
}
function RequestForm({ state, busy, submit }) {
  const [kind, setKind] = useState("force");
  const students = state.people.filter((p) => p.roles.includes("student"));
  const candidates = state.people.filter(
    (p) =>
      p.roles.includes("approver") && !state.panel.some((m) => m.id === p.id),
  );
  return (
    <form
      className="request-form"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const body = {
          kind,
          reason: form.get("reason"),
          publicReason: form.get("publicReason"),
        };
        if (kind === "panel")
          Object.assign(body, {
            replaceId: form.get("replaceId"),
            candidateId: form.get("candidateId"),
          });
        else
          Object.assign(body, {
            courseId: form.get("courseId"),
            studentId: form.get("studentId"),
          });
        submit(body);
      }}
    >
      <div className="form-title">
        <div>
          <div className="eyebrow">REASONED EXCEPTIONS</div>
          <h3>Propose a change</h3>
        </div>
        <span className="approval-badge">Two independent approvals</span>
      </div>
      <div className="form-grid">
        <label>
          Action
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(actionNames).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {kind === "panel" ? (
          <>
            <label>
              Replace member
              <select name="replaceId" required>
                {state.panel.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Eligible replacement
              <select name="candidateId" required>
                <option value="">Select a replacement</option>
                {candidates.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <>
            <label>
              Course
              <select name="courseId" required>
                {state.courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Student
              <select name="studentId" required>
                {students.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label className="reason-field">
          Reviewer details · restricted to staff
          <textarea
            name="reason"
            minLength={5}
            maxLength={2000}
            required
            placeholder="Explain the evidence reviewers should consider."
          />
        </label>
        <label className="reason-field">
          Public explanation · published after approval
          <textarea
            name="publicReason"
            minLength={5}
            maxLength={240}
            required
            placeholder="Provide a brief explanation without private student details."
          />
        </label>
      </div>
      <div className="form-footer">
        <span>
          You cannot approve your own proposal. Course or panel changes may
          require a fresh request.
        </span>
        <button className="button dark" disabled={busy}>
          Submit for review
        </button>
      </div>
    </form>
  );
}
