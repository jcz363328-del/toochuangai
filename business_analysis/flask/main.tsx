import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DashboardClient from "../app/DashboardClient";
import { emptyWorkbookData } from "../app/data/empty-workbook-data";
import "../app/globals.css";

const root = document.getElementById("root");

if (!root) throw new Error("Dashboard root element was not found");

createRoot(root).render(
  <StrictMode>
    <DashboardClient data={emptyWorkbookData} />
  </StrictMode>,
);
