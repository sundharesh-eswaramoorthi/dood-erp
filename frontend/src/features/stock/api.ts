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

export async function listGodowns(): Promise<Godown[]> {
  const { data } = await api.get<Godown[]>("/api/v1/godowns");
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
