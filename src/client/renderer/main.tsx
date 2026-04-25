import React from "react";
import { createRoot } from "react-dom/client";
import { AppProvider } from "./context/AppContext";
import { App } from "./App";
import { BootGate } from "./components/BootGate";
import "./styles/main.css";

const root = document.getElementById("root")!;
createRoot(root).render(
  <AppProvider>
    <BootGate>
      <App />
    </BootGate>
  </AppProvider>
);
