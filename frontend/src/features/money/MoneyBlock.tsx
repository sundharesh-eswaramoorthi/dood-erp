import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Box,
  Button,
  Divider,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import {
  EMPTY_SPLIT,
  splitTotal,
  type MoneyHeader,
  type MoneyTotals,
  type PaymentSplit,
} from "./api";

export interface Account {
  id: number;
  name: string;
}

export interface PaymentTypeRef {
  id: number;
  name: string;
}

/** The v2 §3 header money fields: entry mode, overall discount, charges, payment. */
export function MoneyFields({
  value,
  onChange,
  accounts,
  paymentTypes,
  compact,
}: {
  value: MoneyHeader;
  onChange: (m: MoneyHeader) => void;
  accounts: Account[];
  paymentTypes?: PaymentTypeRef[];
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
      <PaymentSplits
        value={value.payments}
        onChange={(payments) => onChange({ ...value, payments })}
        accounts={accounts}
        paymentTypes={paymentTypes ?? []}
      />

      <TextField
        size="small"
        label="Remarks"
        value={value.remarks}
        onChange={(e) => set("remarks", e.target.value)}
        fullWidth
      />
    </Stack>
  );
}

/** v2 §3 split payment: part cash, part UPI, part card is one document, not
 *  three. Each row says where the money landed AND how it was taken — the same
 *  bank account can receive a card swipe and a transfer, and the payment-mode
 *  reports need to tell them apart. */
export function PaymentSplits({
  value,
  onChange,
  accounts,
  paymentTypes,
  label = "Paid now",
}: {
  value: PaymentSplit[];
  onChange: (splits: PaymentSplit[]) => void;
  accounts: Account[];
  paymentTypes: PaymentTypeRef[];
  label?: string;
}) {
  const patch = (i: number, changes: Partial<PaymentSplit>) =>
    onChange(value.map((p, idx) => (idx === i ? { ...p, ...changes } : p)));

  const add = () =>
    onChange([
      ...value,
      { ...EMPTY_SPLIT, account_id: accounts[0]?.id ?? null },
    ]);

  const total = splitTotal(value);

  if (value.length === 0) {
    return (
      <Box>
        <Button size="small" onClick={add} disabled={!accounts.length}>
          + {label}
        </Button>
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          leave empty for a fully unpaid document
        </Typography>
      </Box>
    );
  }

  return (
    <Stack spacing={1}>
      {value.map((p, i) => (
        <Stack key={i} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center">
          <TextField
            size="small" label="Into account" select value={p.account_id ?? ""}
            onChange={(e) => patch(i, { account_id: Number(e.target.value) })}
            sx={{ minWidth: 160 }}
          >
            {accounts.map((a) => (<MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>))}
          </TextField>
          <TextField
            size="small" label="Taken as" select value={p.payment_type_id ?? ""}
            onChange={(e) => patch(i, { payment_type_id: Number(e.target.value) })}
            sx={{ minWidth: 140 }}
          >
            {paymentTypes.map((t) => (<MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>))}
          </TextField>
          <TextField
            size="small" label="Amount" value={p.amount}
            onChange={(e) => patch(i, { amount: e.target.value })}
            sx={{ width: 110 }}
          />
          <TextField
            size="small" label="Reference" placeholder="cheque / UPI no"
            value={p.reference}
            onChange={(e) => patch(i, { reference: e.target.value })}
            sx={{ width: 150 }}
          />
          <IconButton size="small" onClick={() => onChange(value.filter((_, idx) => idx !== i))}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Stack direction="row" spacing={2} alignItems="center">
        <Button size="small" onClick={add}>+ Add payment</Button>
        <Typography variant="caption" color="text.secondary">
          {label} ₹{total.toFixed(2)} across {value.length} tender{value.length === 1 ? "" : "s"}
        </Typography>
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
