import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import NodeBoard from "./NodeBoard";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <NodeBoard />
  </StrictMode>,
);
