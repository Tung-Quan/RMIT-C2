import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { TideCloakContextProvider } from "@tidecloak/react";
import App, { SetupScreen } from "./App.jsx";
import "./style.css";

function Bootstrap() {
  const [adapter, setAdapter] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/tidecloak.json", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (
          !response.ok ||
          !response.headers.get("content-type")?.includes("json")
        )
          throw new Error("The Tide adapter has not been exported yet.");
        return response.json();
      })
      .then((config) => {
        if (!config.jwk?.keys?.length || !config.resource || !config.realm)
          throw new Error("The Tide adapter is incomplete.");
        setAdapter(config);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);
  if (error) return <SetupScreen message={error} />;
  if (!adapter)
    return (
      <main className="loading" role="status">
        Loading FairEnrol…
      </main>
    );
  return (
    <TideCloakContextProvider
      config={{ ...adapter, useDPoP: { mode: "strict", alg: "ES256" } }}
    >
      <App />
    </TideCloakContextProvider>
  );
}
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Bootstrap />
  </React.StrictMode>,
);
