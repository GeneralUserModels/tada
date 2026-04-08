import React from "react";
import { createRoot } from "react-dom/client";
import { Overlay } from "./components/overlay/Overlay";

const root = document.getElementById("root")!;
createRoot(root).render(<Overlay />);
