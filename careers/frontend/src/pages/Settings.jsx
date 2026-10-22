import {
  Bell,
  EyeOff,
  LayoutDashboard,
  LockKeyhole,
  Mail,
  MessageCircle,
  Monitor,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Alert } from "../components/Alert";
import { CandidateButton, CandidatePage, cx } from "../components/candidate/CandidateUI";
import { useAuth } from "../context/AuthContext";
import { settingsSchema } from "../validation/forms";

const SETTINGS_STORAGE_KEY = "fairenrol_careers_workspace_settings";

const defaultSettings = {
  density: "comfortable",
  startPage: "role-home",
  emailDigest: true,
  chatNotifications: true,
  deadlineReminders: true,
  privacyMode: true
};

function loadSettings() {
  try {
    const rawValue = localStorage.getItem(SETTINGS_STORAGE_KEY);
    const parsed = rawValue ? { ...defaultSettings, ...JSON.parse(rawValue) } : defaultSettings;
    const result = settingsSchema.safeParse(parsed);
    return result.success ? result.data : defaultSettings;
  } catch {
    return defaultSettings;
  }
}

function ToggleRow({ icon: Icon, title, description, checked, onChange }) {
  return (
    <label className="grid cursor-pointer gap-3 rounded-lg px-3 py-3 transition hover:bg-[var(--candidate-surface-soft)] sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:items-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white text-[var(--candidate-primary)] ring-1 ring-[var(--candidate-border)]">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-extrabold text-[var(--candidate-ink-strong)]">{title}</span>
        <span className="mt-1 block text-sm leading-6 text-[var(--candidate-muted)]">{description}</span>
      </span>
      <span className="relative inline-flex h-7 w-12 items-center rounded-full bg-[var(--candidate-border-strong)] p-1 transition has-[:checked]:bg-[var(--candidate-primary)]">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="peer sr-only"
        />
        <span className="h-5 w-5 rounded-full bg-white shadow-sm transition peer-checked:translate-x-5" />
      </span>
    </label>
  );
}

function ChoiceButton({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "min-h-11 rounded-lg px-4 text-sm font-extrabold transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[rgba(0,141,218,0.14)]",
        active
          ? "bg-[var(--candidate-primary)] text-white shadow-sm"
          : "bg-white text-[var(--candidate-ink)] ring-1 ring-[var(--candidate-border)] hover:bg-[var(--candidate-surface-soft)]"
      )}
    >
      {children}
    </button>
  );
}

function PreferenceSection({ eyebrow, title, children }) {
  return (
    <section className="candidate-surface p-4 sm:p-5">
      <div className="mb-4">
        <p className="candidate-eyebrow">{eyebrow}</p>
        <h2 className="mt-1 text-lg font-extrabold text-[var(--candidate-ink-strong)]">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function Settings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(loadSettings);
  const [saved, setSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    if (!saved) return undefined;
    const timeout = window.setTimeout(() => setSaved(false), 2400);
    return () => window.clearTimeout(timeout);
  }, [saved]);

  const displayName = useMemo(() => user?.full_name || user?.email?.split("@")[0] || "Workspace user", [user]);

  function updateSetting(key, value) {
    setSettings((current) => {
      const nextSettings = { ...current, [key]: value };
      const result = settingsSchema.safeParse(nextSettings);
      return result.success ? result.data : current;
    });
  }

  function handleSave() {
    const result = settingsSchema.safeParse(settings);
    if (!result.success) {
      setSettings(defaultSettings);
      setSaved(true);
      return;
    }
    setIsSaving(true);
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    window.setTimeout(() => {
      setIsSaving(false);
      setSaved(true);
    }, 180);
  }

  return (
    <CandidatePage>
      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.62fr)_minmax(18rem,0.38fr)] lg:items-end">
        <div>
          <p className="candidate-eyebrow">Settings</p>
          <h1 className="candidate-title">Tune the workspace without leaking internals.</h1>
          <p className="candidate-copy">
            Keep the interface focused, set notification preferences, and review account context. Private environment values stay hidden by design.
          </p>
        </div>
        <div className="candidate-soft-surface p-4">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--candidate-ink-strong)] text-white">
              <UserRound className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-base font-extrabold text-[var(--candidate-ink-strong)]">{displayName}</p>
              <p className="truncate text-sm font-bold text-[var(--candidate-muted)]">{user?.email}</p>
            </div>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <span className="rounded-lg bg-white px-3 py-2 text-sm font-extrabold text-[var(--candidate-ink)] ring-1 ring-[var(--candidate-border)]">
              Role: {user?.role || "user"}
            </span>
            <span className="rounded-lg bg-white px-3 py-2 text-sm font-extrabold text-[var(--candidate-ink)] ring-1 ring-[var(--candidate-border)]">
              Local preferences
            </span>
          </div>
        </div>
      </section>

      {saved && <Alert>Settings saved for this browser.</Alert>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="grid gap-5">
          <PreferenceSection eyebrow="Appearance" title="Workspace display">
            <div className="grid gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-ink-strong)]">
                  <Monitor className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                  Density
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <ChoiceButton active={settings.density === "comfortable"} onClick={() => updateSetting("density", "comfortable")}>
                    Comfortable
                  </ChoiceButton>
                  <ChoiceButton active={settings.density === "compact"} onClick={() => updateSetting("density", "compact")}>
                    Compact
                  </ChoiceButton>
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-ink-strong)]">
                  <LayoutDashboard className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                  Start page
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <ChoiceButton active={settings.startPage === "role-home"} onClick={() => updateSetting("startPage", "role-home")}>
                    Role home
                  </ChoiceButton>
                  <ChoiceButton active={settings.startPage === "chat"} onClick={() => updateSetting("startPage", "chat")}>
                    Chat
                  </ChoiceButton>
                  <ChoiceButton active={settings.startPage === "search"} onClick={() => updateSetting("startPage", "search")}>
                    Search
                  </ChoiceButton>
                </div>
              </div>
            </div>
          </PreferenceSection>

          <PreferenceSection eyebrow="Notifications" title="Signal preferences">
            <div className="divide-y divide-[var(--candidate-border)]">
              <ToggleRow
                icon={Mail}
                title="Email digest"
                description="Receive a concise summary of deadlines and recent hiring activity."
                checked={settings.emailDigest}
                onChange={(value) => updateSetting("emailDigest", value)}
              />
              <ToggleRow
                icon={MessageCircle}
                title="Chat notifications"
                description="Highlight new direct and group messages inside the workspace."
                checked={settings.chatNotifications}
                onChange={(value) => updateSetting("chatNotifications", value)}
              />
              <ToggleRow
                icon={Bell}
                title="Deadline reminders"
                description="Surface upcoming application deadlines before they become urgent."
                checked={settings.deadlineReminders}
                onChange={(value) => updateSetting("deadlineReminders", value)}
              />
            </div>
          </PreferenceSection>
        </div>

        <aside className="grid gap-5 content-start">
          <PreferenceSection eyebrow="Privacy" title="Protected surface">
            <div className="space-y-4">
              <ToggleRow
                icon={EyeOff}
                title="Hide private configuration"
                description="Keep API URLs, secrets, keys, and internal environment values out of the visual workspace."
                checked={settings.privacyMode}
                onChange={(value) => updateSetting("privacyMode", value)}
              />
              <div className="rounded-lg bg-[var(--candidate-surface-soft)] p-4">
                <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-ink-strong)]">
                  <ShieldCheck className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
                  What stays hidden
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--candidate-muted)]">
                  This page shows account and preference state only. Secret keys, tokens, database strings, and deployment configuration are intentionally not rendered.
                </p>
              </div>
            </div>
          </PreferenceSection>

          <PreferenceSection eyebrow="Controls" title="Save preferences">
            <div className="space-y-3">
              <CandidateButton type="button" onClick={handleSave} className="w-full" disabled={isSaving}>
                <Save className="h-4 w-4" aria-hidden="true" />
                {isSaving ? "Saving settings" : "Save settings"}
              </CandidateButton>
              <button
                type="button"
                onClick={() => setSettings(defaultSettings)}
                className="candidate-button candidate-button--secondary w-full"
              >
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                Reset defaults
              </button>
            </div>
          </PreferenceSection>

          <div className="candidate-soft-surface p-4">
            <div className="flex items-center gap-2 text-sm font-extrabold text-[var(--candidate-ink-strong)]">
              <LockKeyhole className="h-4 w-4 text-[var(--candidate-primary)]" aria-hidden="true" />
              Security note
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--candidate-muted)]">
              Manage actual secrets on the server or deployment platform, never through frontend screens.
            </p>
          </div>
        </aside>
      </div>
    </CandidatePage>
  );
}
