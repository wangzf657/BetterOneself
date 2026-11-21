import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import LearnPage from "./features/learn/LearnPage";
import SettingsPage from "./features/settings/SettingsPage";
import NewStudyPage from "./features/studies/NewStudyPage";
import StudiesPage from "./features/studies/StudiesPage";
import TreePage from "./features/tree/TreePage";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <StudiesPage /> }, // 访问 / 重定向到 /studies（页面清单 1.1）
      { path: "studies", element: <StudiesPage /> },
      { path: "studies/new", element: <NewStudyPage /> },
      { path: "studies/:studyId", element: <TreePage /> },
      { path: "studies/:studyId/learn/:nodeId", element: <LearnPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster position="top-center" richColors />
    </QueryClientProvider>
  </React.StrictMode>,
);
