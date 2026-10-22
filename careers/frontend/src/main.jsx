import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { TideCloakContextProvider } from "@tidecloak/react";
import App from "./App.jsx";
import {AuthProvider} from "./context/AuthContext.jsx";
import {WorkspaceBar} from "./components/WorkspaceBar.jsx";
import "./index.css";
class WorkspaceBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="tide-login" role="alert"><h1>Restore your workspace</h1><p>The workspace could not be displayed. Refresh to restore the session.</p><button onClick={() => location.reload()}>Refresh workspace</button><a href="/">Return to FairEnrol</a></main>;
    return this.props.children;
  }
}
function Bootstrap() {
  const [adapter, setAdapter] = useState(null), [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/tidecloak.json", { cache: "no-store", signal: controller.signal }).then(r => {
      if (!r.ok) throw new Error("Tide configuration is unavailable");
      return r.json();
    }).then(config => { if (!controller.signal.aborted) setAdapter(config); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  const config = useMemo(() => adapter && ({ ...adapter, useDPoP: { mode: "strict", alg: "ES256" } }), [adapter]);
  if (error) return <main className="tide-login" role="alert">{error} <a href="/">Return to FairEnrol</a></main>;
  if (!config) return <main role="status">Connecting to TideCloak…</main>;
  // The SDK owns an imperative iframe lifecycle. Mount that boundary once;
  // retain React development checks for the application beneath it.
  return <TideCloakContextProvider config={config}><BrowserRouter basename="/careers" future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><AuthProvider><React.StrictMode><WorkspaceBar/><App/></React.StrictMode></AuthProvider></BrowserRouter></TideCloakContextProvider>;
}
ReactDOM.createRoot(document.getElementById("root")).render(<WorkspaceBoundary><Bootstrap/></WorkspaceBoundary>);
