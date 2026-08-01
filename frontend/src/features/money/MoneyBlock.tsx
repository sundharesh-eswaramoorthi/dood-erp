import {
  Box,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { type MoneyHeader, type MoneyTotals } from "./api";

export interface Account {
  id: number;
  name: string;
}

/** The v2 §3 header money fields: entry mode, overall discount, charges, payment. */
export function MoneyFields({
  value,
  onChange,
  accounts,
  compact,
}: {
  value: MoneyHeader;
  onChange: (m: MoneyHeader) => void;
  accounts: Account[];
  compact?: boolean;
}) {
  const set = (k: keyof MoneyHeader, v: unknown) => onChange({ ...value, [k]: v });
  const w = compact ? 110 : 130;

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Price mode"
          select
          value={value.price_mode}
          onChange={(e) => set("price_mode", e.target.value)}
          sx={{ width: 170 }}
          helperText={value.price_mode === "inclusive" ? "rates include GST" : "GST added on top"}
        >
          <MenuItem value="exclusive">Without tax</MenuItem>
          <MenuItem value="inclusive">With tax</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="Overall disc %"
          value={value.discount_pct}
          onChange={(e) => set("discount_pct", e.target.value)}
          sx={{ width: w }}
          disabled={!!value.discount_amount}
        />
        <TextField
          size="small"
          label="Overall disc ₹"
          value={value.discount_amount ?? ""}
          onChange={(e) => set("discount_amount", e.target.value)}
          sx={{ width: w }}
          helperText="wins over %"
        />
        <TextField
          size="small"
          label="Card charges"
          value={value.card_charges}
          onChange={(e) => set("card_charges", e.target.value)}
          sx={{ width: w }}
        />
        <TextField
          size="small"
          label="Round off"
          value={value.round_off ?? ""}
          onChange={(e) => set("round_off", e.target.value)}
          sx={{ width: w }}
          helperText="blank = auto"
        />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Paid now"
          value={value.paid_amount}
          onChange={(e) => set("paid_amount", e.target.value)}
          sx={{ width: w }}
        />
        <TextField
          size="small"
          label="Payment type"
          select
          value={value.payment_account_id ?? ""}
          onChange={(e) => set("payment_account_id", Number(e.target.value))}
          sx={{ width: 190 }}
          disabled={!value.paid_amount}
          helperText={value.paid_amount ? "required" : "set a paid amount first"}
        >
          {accounts.map((a) => (
            <MenuItem key={a.id} value={a.id}>
              {a.name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Remarks"
          value={value.remarks}
          onChange={(e) => set("remarks", e.target.value)}
          sx={{ flex: 1, minWidth: 200 }}
        />
      </Stack>
    </Stack>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={4}>
      <Typography variant="body2" color={strong ? "text.primary" : "text.secondary"} fontWeight={strong ? 700 : 400}>
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={strong ? 700 : 500} sx={{ fontVariantNumeric: "tabular-nums" }}>
        ₹{value}
      </Typography>
    </Stack>
  );
}

/** Live totals, computed by the server so they match the posted document exactly. */
export function MoneyTotalsPanel({ totals }: { totals: MoneyTotals | null | undefined }) {
  if (!totals) {
    return (
      <Typography variant="body2" color="text.secondary">
        Add a line to see the totals.
      </Typography>
    );
  }
  const nz = (v: string) => Number(v) !== 0;
  return (
    <Box sx={{ minWidth: 260 }}>
      <Stack spacing={0.5}>
        <Row label="Gross" value={totals.gross_total} />
        {nz(totals.line_discount_total) && <Row label="Line discounts" value={`-${totals.line_discount_total}`} />}
        {nz(totals.discount_amount) && <Row label="Overall discount" value={`-${totals.discount_amount}`} />}
        <Row label="Taxable" value={totals.taxable_total} />
        {nz(totals.cgst_total) && <Row label="CGST" value={totals.cgst_total} />}
        {nz(totals.sgst_total) && <Row label="SGST" value={totals.sgst_total} />}
        {nz(totals.igst_total) && <Row label="IGST" value={totals.igst_total} />}
        {nz(totals.card_charges) && <Row label="Card charges" value={totals.card_charges} />}
        {nz(totals.round_off) && <Row label="Round off" value={totals.round_off} />}
        <Divider sx={{ my: 0.5 }} />
        <Row label="Grand total" value={totals.grand_total} strong />
        {nz(totals.paid_amount) && (
          <>
            <Row label="Paid" value={`-${totals.paid_amount}`} />
            <Row label="Balance" value={totals.balance_amount} strong />
          </>
        )}
      </Stack>
    </Box>
  );
}
