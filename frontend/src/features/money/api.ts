import { api } from "../../lib/api";

/** One tender against a document (v2 §3 split payment): where the money landed
 *  and how it was taken. */
export interface PaymentSplit {
  account_id: number | null;
  payment_type_id: number | null;
  amount: string;
  reference: string;
}

export const EMPTY_SPLIT: PaymentSplit = {
  account_id: null,
  payment_type_id: null,
  amount: "",
  reference: "",
};

/** A tender is worth sending once it names an account and an amount. */
export function usableSplits(splits: PaymentSplit[]): PaymentSplit[] {
  return splits.filter((p) => p.account_id != null && Number(p.amount) > 0);
}

export function splitTotal(splits: PaymentSplit[]): number {
  return usableSplits(splits).reduce((n, p) => n + Number(p.amount), 0);
}

/** Header money block shared by every invoice-shaped document (v2 §3/§4). */
export interface MoneyHeader {
  price_mode: string;
  discount_pct: string;
  discount_amount: string | null;
  card_charges: string;
  round_off: string | null;
  paid_amount: string;
  payment_account_id: number | null;
  /** v2 §3: several tenders on one document. When non-empty this replaces
   *  paid_amount/payment_account_id, and the server derives paid_amount. */
  payments: PaymentSplit[];
  remarks: string;
}

export const EMPTY_MONEY: MoneyHeader = {
  price_mode: "exclusive",
  discount_pct: "",
  discount_amount: "",
  card_charges: "",
  round_off: "",
  paid_amount: "",
  payment_account_id: null,
  payments: [],
  remarks: "",
};

/** Strip the blanks so the API sees "not supplied" rather than "zero". */
export function moneyPayload(m: MoneyHeader) {
  const splits = usableSplits(m.payments);
  return {
    price_mode: m.price_mode,
    discount_pct: m.discount_pct || "0",
    discount_amount: m.discount_amount || undefined,
    card_charges: m.card_charges || "0",
    round_off: m.round_off ? m.round_off : undefined,   // blank/null => auto
    // With tenders, paid_amount is the server's business — sending both risks
    // them disagreeing, which it rejects outright.
    ...(splits.length
      ? {
          payments: splits.map((p) => ({
            account_id: p.account_id,
            payment_type_id: p.payment_type_id ?? undefined,
            amount: p.amount,
            reference: p.reference || undefined,
          })),
        }
      : {
          paid_amount: m.paid_amount || "0",
          payment_account_id: m.paid_amount ? m.payment_account_id ?? undefined : undefined,
        }),
    remarks: m.remarks || undefined,
  };
}

export interface MoneyTotals {
  gross_total: string;
  line_discount_total: string;
  discount_amount: string;
  taxable_total: string;
  tax_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  card_charges: string;
  round_off: string;
  grand_total: string;
  paid_amount: string;
  balance_amount: string;
}

export interface PreviewLine {
  qty: string;
  rate: string;
  gst_rate?: string;
  discount_pct?: string;
  discount_amount?: string;
}

export interface PreviewResult {
  lines: { taxable: string; tax: string; line_total: string }[];
  totals: MoneyTotals | null;
}

/** Ask the server to run the real money engine — no duplicate maths here. */
export async function previewMoney(
  lines: PreviewLine[],
  header: MoneyHeader,
  supply_type: string,
): Promise<PreviewResult> {
  const { data } = await api.post<PreviewResult>("/api/v1/money/preview", {
    ...moneyPayload(header),
    supply_type,
    lines: lines.map((l) => ({
      qty: l.qty || "0",
      rate: l.rate || "0",
      gst_rate: l.gst_rate || "0",
      discount_pct: l.discount_pct || "0",
      discount_amount: l.discount_amount || undefined,
    })),
  });
  return data;
}
