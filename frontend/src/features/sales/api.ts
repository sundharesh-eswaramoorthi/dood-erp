import { api } from "../../lib/api";

export interface SaleOrder {
  id: number;
  doc_no: string | null;
  status: string;
  customer_id: number;
  order_date?: string;
}

export async function createOrder(payload: {
  customer_id: number;
  lines: { product_id: number; godown_id: number; entered_qty: string; entered_unit_id: number; rate: string }[];
}): Promise<SaleOrder> {
  const { data } = await api.post<SaleOrder>("/api/v1/sales/orders", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function listOrders(): Promise<SaleOrder[]> {
  const { data } = await api.get<SaleOrder[]>("/api/v1/sales/orders");
  return data;
}

export async function cancelOrder(id: number): Promise<SaleOrder> {
  const { data } = await api.post<SaleOrder>(`/api/v1/sales/orders/${id}/cancel`);
  return data;
}
