"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WorkbookData } from "../lib/dashboard";
import {
  createWorkbookSnapshotSource,
  fetchLiveDashboard,
  liveErrorMessage,
  LiveDashboardError,
  type FormulaTrace,
  type LiveDashboardSource,
  type LivePhase,
} from "../lib/live-dashboard";

const POLL_INTERVAL_MS = 60_000;

export interface UseLiveDashboardResult {
  data: WorkbookData;
  formulas: FormulaTrace[];
  source: LiveDashboardSource;
  phase: LivePhase;
  error: string | null;
  refresh: (force?: boolean) => Promise<void>;
}

interface LiveState {
  data: WorkbookData;
  formulas: FormulaTrace[];
  source: LiveDashboardSource;
  phase: LivePhase;
  error: string | null;
}

const isAbortError = (error: unknown) =>
  error instanceof DOMException && error.name === "AbortError";

function degradedSource(
  source: LiveDashboardSource,
  error: unknown,
): LiveDashboardSource {
  const databaseFailure =
    error instanceof LiveDashboardError && error.code.startsWith("DB_");
  const notConfigured =
    error instanceof LiveDashboardError && error.code === "DB_NOT_CONFIGURED";

  return {
    ...source,
    mode:
      source.mode === "workbook-snapshot" ? "workbook-snapshot" : "memory-cache",
    stale: true,
    warning: liveErrorMessage(error),
    database: {
      ...source.database,
      configured: notConfigured ? false : source.database.configured,
      status: databaseFailure ? "down" : "unknown",
      latencyMs: null,
    },
  };
}

export function useLiveDashboard(
  initialData: WorkbookData,
  period: string,
): UseLiveDashboardResult {
  const [state, setState] = useState<LiveState>(() => ({
    data: initialData,
    formulas: [],
    source: createWorkbookSnapshotSource(initialData),
    phase: "degraded",
    error: null,
  }));
  const requestId = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(
    async (force = false) => {
      const id = ++requestId.current;
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      setState((current) => ({ ...current, phase: "refreshing", error: null }));

      try {
        const envelope = await fetchLiveDashboard(period, {
          force,
          signal: controller.signal,
        });
        if (id !== requestId.current) return;
        setState({
          data: envelope.data,
          formulas: envelope.formulas,
          source: envelope.source,
          phase:
            envelope.source.stale || envelope.source.mode === "workbook-snapshot"
              ? "degraded"
              : "live",
          error: null,
        });
      } catch (error) {
        if (isAbortError(error) || id !== requestId.current) return;
        setState((current) => ({
          ...current,
          source: degradedSource(current.source, error),
          phase: "degraded",
          error: liveErrorMessage(error),
        }));
      } finally {
        if (id === requestId.current) activeRequest.current = null;
      }
    },
    [period],
  );

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const stopPolling = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const startPolling = () => {
      stopPolling();
      if (document.hidden) return;
      timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    };
    const onVisibilityChange = () => {
      if (document.hidden) {
        stopPolling();
        activeRequest.current?.abort();
        return;
      }
      void refresh();
      startPolling();
    };

    if (!document.hidden) void refresh();
    startPolling();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      activeRequest.current?.abort();
    };
  }, [refresh]);

  return { ...state, refresh };
}
