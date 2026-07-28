import { api } from "../../lib/api";

export interface BillLineIn {
  product_id: number;
  entered_qty: string;
  entered_unit_id: number;
  rate: string;
  gst_rate?: string;
}

export interface PurchaseBillCreate {
  supplier_id: number;
  godown_id: number;
  supply_type?: string;
  supplier_invoice_no?: string;
  lines: BillLineIn[];
}

export interface PurchaseBill {
  id: number;
  doc_no: string | null;
  status: string;
  supplier_id: number;
  taxable_total?: string;
  tax_total?: string;
  grand_total: string;
}

export async function createBill(payload: PurchaseBillCreate): Promise<PurchaseBill> {
  const { data } = await api.post<PurchaseBill>("/api/v1/purchase/bills", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function listBills(): Promise<PurchaseBill[]> {
  const { data } = await api.get<PurchaseBill[]>("/api/v1/purchase/bills");
  return data;
}
