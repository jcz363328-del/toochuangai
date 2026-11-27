export interface FiscalRankingRow {
  rank: number;
  key: string;
  name: string;
  department?: string;
  operator?: string;
  stores: number;
  storeNames: string[];
  fullYearTarget: number | null;
  ytdTarget: number | null;
  actual: number | null;
  achievementRate: number | null;
  gap: number | null;
  gapRate: number | null;
}

export interface FiscalOverviewPayload {
  fiscalYear: string;
  scope: {
    role: "business_owner" | "department_leader" | "member" | "ratio_viewer";
    department: string | null;
    operator: string | null;
    canViewAmounts: boolean;
  };
  filters: {
    department: string | null;
    departments: string[];
    periodType: "annual" | "quarter" | "month";
    period: string;
    periodLabel: string;
    periodOptions: Array<{ value: string; label: string }>;
  };
  period: {
    start: string | null;
    end: string | null;
    latestActualDate: string | null;
    sourceLatestActualDate: string | null;
    elapsedMonths: number;
    totalMonths: number;
    targetProrated: boolean;
    targetElapsedDays: number | null;
    targetMonthDays: number | null;
  };
  overall: {
    fullYearTarget: number | null;
    periodTarget: number | null;
    ytdTarget: number | null;
    actual: number | null;
    achievementRate: number | null;
    periodCompletionRate: number | null;
    annualProgressRate: number | null;
    companyFiscalAchievementRate?: number | null;
    gap: number | null;
    gapRate: number | null;
    periodRemaining: number | null;
    periodRemainingRate: number | null;
    remainingToAnnual: number | null;
    remainingRate: number | null;
  };
  monthly: Array<{
    period: string;
    target: number | null;
    targetToDate: number | null;
    actual: number | null;
    cumulativeTarget: number | null;
    cumulativeTargetToDate: number | null;
    cumulativeActual: number | null;
    achievementRate: number | null;
  }>;
  departments: FiscalRankingRow[];
  stores?: FiscalRankingRow[];
  people: FiscalRankingRow[];
  quality: {
    targetRows: number;
    targetStores: number;
    storesWithActual: number;
    storesWithoutActual: number;
    matchedStoreCount: number;
    excludedActualStoreCount: number;
  };
  source: {
    target: string;
    actual: string;
    join: string;
    fetchedAt: string;
  };
}

interface FiscalOverviewError {
  error?: { message?: string };
}

export interface FiscalOverviewFilters {
  department?: string;
  periodType?: "annual" | "quarter" | "month";
  period?: string;
}

export async function fetchFiscalOverview(filters: FiscalOverviewFilters = {}): Promise<FiscalOverviewPayload> {
  const query = new URLSearchParams({
    fiscal_year: "2026-2027",
    period_type: filters.periodType || "annual",
  });
  if (filters.department) query.set("department", filters.department);
  if (filters.period) query.set("period", filters.period);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45_000);
  let response: Response;
  try {
    response = await fetch(`/api/ai/business-analysis/fiscal-overview?${query}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new Error("财年缓存读取超时，请稍后重试");
    }
    throw reason;
  } finally {
    window.clearTimeout(timeout);
  }
  const payload = await response.json().catch(() => null) as FiscalOverviewPayload | FiscalOverviewError | null;
  if (!response.ok) {
    const message = payload && "error" in payload ? payload.error?.message : null;
    throw new Error(message || `财年首页加载失败（HTTP ${response.status}）`);
  }
  if (!payload || !("overall" in payload)) throw new Error("财年首页返回了无效数据");
  return payload as FiscalOverviewPayload;
}
