import { existsSync } from "node:fs";

const repositoryData = new URL("../../../../business_analysis/data/", import.meta.url);
export const dataDirectory = existsSync(repositoryData)
  ? repositoryData
  : new URL("../data/", import.meta.url);
