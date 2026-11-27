import DashboardClient from "./DashboardClient";
import workbookData from "./data/workbook-data.json";
import type { WorkbookData } from "./lib/dashboard";

export default function Home() {
  return <DashboardClient data={workbookData as WorkbookData} />;
}
