import { apiRequest, queryString } from "./client";
import type { MonitoringPeriod, MonitoringResponse } from "./types";

export const monitoringApi = {
  aggregate: (period: MonitoringPeriod, signal?: AbortSignal) =>
    apiRequest<MonitoringResponse>(`/api/admin/monitoring${queryString({ period })}`, { signal }),
};
