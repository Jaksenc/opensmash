import React, { lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
const OgStudio = lazy(() => import("./OgStudio.jsx"));

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {pathname === "/og-studio" ? (
      <Suspense fallback={<main className="og-studio-loading">Loading Open Graph Studio…</main>}>
        <OgStudio />
      </Suspense>
    ) : <App />}
  </React.StrictMode>,
);
