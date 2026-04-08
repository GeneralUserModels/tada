import React from "react";
import { createRoot } from "react-dom/client";
import { AppProvider } from "./context/AppContext";
import { App } from "./App";
import "./styles/main.css";

const root = document.getElementById("root")!;
createRoot(root).render(
  <AppProvider>
    <App />
  </AppProvider>
);
