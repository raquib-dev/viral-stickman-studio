import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import "./index.css";
import { Layout } from "./components/Layout";
import { ProjectProvider } from "./lib/useProject";
import Activity from "./pages/Activity";
import Discover from "./pages/Discover";
import Home from "./pages/Home";
import Learn from "./pages/Learn";
import Niche from "./pages/Niche";
import Package from "./pages/Package";
import Patterns from "./pages/Patterns";
import Render from "./pages/Render";
import Settings from "./pages/Settings";
import Studio from "./pages/Studio";
import Topics from "./pages/Topics";

const PAGES: Record<string, () => JSX.Element> = {
  niche: Niche, discover: Discover, patterns: Patterns, topics: Topics, studio: Studio, render: Render,
  package: Package, learn: Learn, activity: Activity,
};

function ProjectRoute() {
  const { slug, page } = useParams();
  const Page = PAGES[page ?? "niche"];
  if (!Page) return <Navigate to={`/p/${slug}/niche`} replace />;
  return (
    <ProjectProvider slug={slug ?? null}>
      <Layout><Page /></Layout>
    </ProjectProvider>
  );
}

function Plain({ children }: { children: React.ReactNode }) {
  return <ProjectProvider slug={null}><Layout>{children}</Layout></ProjectProvider>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Plain><Home /></Plain>} />
        <Route path="/settings" element={<Plain><Settings /></Plain>} />
        <Route path="/p/:slug/:page" element={<ProjectRoute />} />
        <Route path="/p/:slug" element={<ProjectRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
