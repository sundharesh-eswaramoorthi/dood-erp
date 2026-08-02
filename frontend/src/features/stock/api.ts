import { api } from "../../lib/api";

export interface Godown {
  id: number;
  name: string;
  branch_id: number;
}

export interface GodownStock {
  godown_id: number;
  on_hand: string;
  reserved: string;
  available: string;
}

export interface CurrentStock {
  product_id: number;
  branch_id: number;
  total_on_hand: string;
  total_reserved: string;
  total_available: string;
  by_godown: GodownStock[];
}

export interface Movement {
  id: number;
  godown_id: number;
  signed_qty: string;
  unit_cost: string | null;
  movement_type: string;
  source_doc_type: string;
  source_doc_id: number;
  effective_date: string;
}

export interface AdjustmentLineIn {
  product_id: number;
  entered_qty: string;
  entered_unit_id: number;
  unit_cost?: string | null;
}

export interface AdjustmentCreate {
  godown_id: number;
  adj_reason: string;
  lines: AdjustmentLineIn[];
}

export async function listGodowns(allBranches = false): Promise<Godown[]> {
  const { data } = await api.get<Godown[]>("/api/v1/godowns", {
    params: allBranches ? { all_branches: true } : undefined,
  });
  return data;
}

export async function getCurrentStock(productId: number): Promise<CurrentStock> {
  const { data } = await api.get<CurrentStock>("/api/v1/stock/current", {
    params: { product_id: productId },
  });
  return data;
}

export async function getMovements(productId: number): Promise<Movement[]> {
  const { data } = await api.get<Movement[]>("/api/v1/stock/movements", {
    params: { product_id: productId },
  });
  return data;
}

export async function postAdjustment(payload: AdjustmentCreate): Promise<unknown> {
  const { data } = await api.post("/api/v1/stock/adjustments", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function reconcile(): Promise<{ ok: boolean; drift_rows: unknown[] }> {
  const { data } = await api.post<{ ok: boolean; drift_rows: unknown[] }>("/api/v1/stock/reconcile");
  return data;
}

export interface Reorder {
  product_id: number;
  branch_id: number;
  godown_id: number | null;
  min_qty: string;
}

export async function listReorder(): Promise<Reorder[]> {
  const { data } = await api.get<Reorder[]>("/api/v1/stock/reorder-thresholds");
  return data;
}

export async function setReorder(payload: { product_id: number; min_qty: string }): Promise<Reorder> {
  const { data } = await api.post<Reorder>("/api/v1/stock/reorder-thresholds", payload);
  return data;
}

// ---- transfers ----
export interface TransferLine {
  line_no: number;
  product_id: number;
  base_qty: string;
  unit_cost: string | null;
}
export interface Transfer {
  id: number;
  doc_no: string | null;
  status: string;
  from_godown_id: number;
  to_godown_id: number;
  lines: TransferLine[];
}

export async function createTransfer(payload: {
  from_godown_id: number;
  to_godown_id: number;
  lines: { product_id: number; entered_qty: string; entered_unit_id: number }[];
}): Promise<Transfer> {
  const { data } = await api.post<Transfer>("/api/v1/stock/transfers", payload);
  return data;
}
export async function dispatchTransfer(id: number): Promise<Transfer> {
  const { data } = await api.post<Transfer>(`/api/v1/stock/transfers/${id}/dispatch`);
  return data;
}
export async function receiveTransfer(id: number): Promise<Transfer> {
  const { data } = await api.post<Transfer>(`/api/v1/stock/transfers/${id}/receive`);
  return data;
}

// ---- verification (snapshot-delta) ----
export interface VerifyLine {
  line_no: number;
  product_id: number;
  system_qty_at_start: string;
  physical_qty: string | null;
  delta: string | null;
}
export interface Verification {
  id: number;
  doc_no: string | null;
  status: string;
  lines: VerifyLine[];
}

export async function createVerification(payload: {
  godown_id: number;
  lines: { product_id: number; physical_qty: string }[];
}): Promise<Verification> {
  const { data } = await api.post<Verification>("/api/v1/stock/verifications", payload);
  return data;
}
export async function postVerification(id: number): Promise<Verification> {
  const { data } = await api.post<Verification>(`/api/v1/stock/verifications/${id}/post`);
  return data;
}

/** A transfer as it appears in the list (V2.17): header plus its size. */
export interface TransferRow {
  id: number;
  doc_no: string | null;
  status: string;
  from_branch_id: number;
  from_godown_id: number;
  to_branch_id: number;
  to_godown_id: number;
  dispatch_date: string | null;
  receive_date: string | null;
  created_at: string;
  line_count: number;
  total_qty: string;
}

/** `state` is "open" (draft or in transit — someone still has to act) or
 *  "closed" (received or cancelled). */
export async function listTransfers(state?: "open" | "closed"): Promise<TransferRow[]> {
  const { data } = await api.get<TransferRow[]>("/api/v1/stock/transfers", {
    params: state ? { state } : undefined,
  });
  return data;
}
