import { api } from "../../lib/api";

export interface ReportResult {
  summary: Record<string, string | number>;
  rows: Record<string, string | number>[];
}

export async function runReport(
  report: string,
  dateFrom: string,
  dateTo: string,
): Promise<ReportResult> {
  const { data } = await api.get<ReportResult>(`/api/v1/reports/${report}`, {
    params: { date_from: dateFrom, date_to: dateTo },
  });
  return data;
}
