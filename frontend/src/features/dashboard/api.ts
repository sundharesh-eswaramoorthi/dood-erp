import { api } from "../../lib/api";

export interface Dashboard {
  today_sales: string;
  today_purchase: string;
  today_orders: number;
  pending_deliveries: number;
  today_collection: string;
  today_expenses: string;
  current_stock_value: string;
  outstanding_receivable: string;
  outstanding_payable: string;
  petty_cash: string;
  low_stock: { name: string; on_hand: string; min_qty: string }[];
  top_selling: { name: string; qty: string }[];
  recent_activities: { topic: string; payload: Record<string, unknown>; at: string }[];
  cached: boolean;
}

export async function getDashboard(): Promise<Dashboard> {
  const { data } = await api.get<Dashboard>("/api/v1/dashboard");
  return data;
}
