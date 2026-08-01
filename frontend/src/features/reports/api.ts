import { api } from "../../lib/api";

export interface ReportMeta {
  key: string;
  group: string;
  title: string;
}

export interface ReportCatalogue {
  count: number;
  reports: ReportMeta[];
}

export interface ReportResult {
  key: string;
  group: string;
  title: string;
  date_from: string;
  date_to: string;
  summary: Record<string, string | number | null>;
  rows: Record<string, string | number | null>[];
}

export interface ReportFilters {
  date_from: string;
  date_to: string;
  branch_id?: number;
  party_id?: number;
  product_id?: number;
  category_id?: number;
  godown_id?: number;
  payment_type_id?: number;
}

/** The v2 §6 catalogue — the picker is built from this, not hard-coded. */
export async function listReports(): Promise<ReportCatalogue> {
  const { data } = await api.get<ReportCatalogue>("/api/v1/reports");
  return data;
}

export async function runReport(
  report: string,
  filters: ReportFilters,
): Promise<ReportResult> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== null),
  );
  const { data } = await api.get<ReportResult>(`/api/v1/reports/${report}`, { params });
  return data;
}

/** Turn a result into CSV so a report can leave the screen. */
export function toCsv(result: ReportResult): string {
  if (!result.rows.length) return "";
  const cols = Object.keys(result.rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...result.rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}
