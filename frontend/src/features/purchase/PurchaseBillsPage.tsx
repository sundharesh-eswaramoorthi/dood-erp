import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ProductPicker } from "../../components/ProductPicker";
import { errorMessage } from "../../lib/api";
import { listAccounts, listPaymentTypes } from "../accounts/api";
import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import { listParties } from "../parties/api";
import { type ProductUnit } from "../products/api";
import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import { createBill, listBills, type PurchaseBill } from "./api";
import { invalidateDocument } from "../../app/refresh";

/** One editable invoice line (v2 §3: godown, qty, rate, discount, HSN, remarks). */
interface DraftLine {
  product: string;
  /** what the product may be entered in — carried so the unit select and the
   *  payload agree without another lookup */
  units: ProductUnit[];
  unit_id: string;
  godown: string;
  qty: string;
  rate: string;
  gst: string;
  discount_pct: string;
  hsn: string;
  remarks: string;
}

const EMPTY_LINE: DraftLine = {
  product: "", units: [], unit_id: "", godown: "", qty: "", rate: "", gst: "",
  discount_pct: "", hsn: "", remarks: "",
};

export function PurchaseBillsPage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const scope = useBranchScope();
  // godowns of the selected branch only — posting into another
  // branch's godown is refused by the server anyway
  const godowns = { data: scope.godowns };
  const bills = useQuery({ queryKey: [...["purchase-bills"], scope.branchId], queryFn: () => listBills(scope.branchId) });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const [f, setF] = useState({ supplier: "", godown: "" });
  const [lines, setLines] = useState<DraftLine[]>([{ ...EMPTY_LINE }]);
  const [mny, setMny] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (godowns.data?.length && !f.godown) setF((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (parties.data?.length && !f.supplier) setF((s) => ({ ...s, supplier: String(parties.data![0].id) }));
  }, [godowns.data, parties.data, f.godown, f.supplier]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;
  const filled = lines.filter((l) => l.product && l.qty && l.rate);

  // Totals come from the server's money engine so the preview and the posted
  // document can never disagree.
  const preview = useQuery({
    queryKey: ["money-preview", filled, mny],
    queryFn: () =>
      previewMoney(
        filled.map((l) => ({ qty: l.qty, rate: l.rate, gst_rate: l.gst, discount_pct: l.discount_pct })),
        mny,
      ),
    enabled: filled.length > 0,
  });

  const setLine = (i: number, patch: Partial<DraftLine>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  const create = useMutation({
    mutationFn: () =>
      createBill({
        supplier_id: Number(f.supplier),
        branch_id: scope.branchId,
        godown_id: Number(f.godown),
        ...moneyPayload(mny),
        lines: filled.map((l) => ({
          product_id: Number(l.product),
          godown_id: Number(l.godown || f.godown),
          entered_qty: l.qty,
          entered_unit_id: Number(l.unit_id),
          rate: l.rate,
          gst_rate: l.gst || undefined,
          discount_pct: l.discount_pct || undefined,
          hsn_code: l.hsn || undefined,
          remarks: l.remarks || undefined,
        })),
      }),
    onSuccess: (b) => {
      setMsg(
        `Posted ${b.doc_no}: grand total ₹${b.grand_total}` +
          (Number(b.paid_amount ?? 0) ? ` · paid ₹${b.paid_amount} · balance ₹${b.balance_amount}` : ""),
      );
      setLines([{ ...EMPTY_LINE }]);
      setMny({ ...EMPTY_MONEY });
      qc.invalidateQueries({ queryKey: ["purchase-bills"] });
      invalidateDocument(qc);
    },
    onError: (e: unknown) => setMsg(errorMessage(e, "Bill failed")),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Purchase bills</Typography>
        <Typography color="text.secondary">
          Goods in from a supplier: stock rises at the post-discount cost, the supplier is
          credited, and anything paid now leaves an account — one transaction.
        </Typography>
      </Box>
      <BranchFilter
        value={scope.branch}
        onChange={scope.setBranch}
        branches={scope.branches}
        helperText="goods arrive into this branch"
      />
      {msg && (
        <Alert severity={msg.startsWith("Posted") ? "success" : "error"} onClose={() => setMsg(null)}>
          {msg}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            New purchase bill
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (f.supplier && filled.length) create.mutate();
            }}
          >
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField label="Supplier" select value={f.supplier} onChange={(e) => setF({ ...f, supplier: e.target.value })} sx={{ flex: 1, minWidth: 180 }}>
                  {(parties.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Default godown" select value={f.godown} onChange={(e) => setF({ ...f, godown: e.target.value })} sx={{ width: 190 }} helperText="lines can override">
                  {(godowns.data ?? []).map((g) => (
                    <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                  ))}
                </TextField>
              </Stack>

              <Divider textAlign="left">
                <Typography variant="caption" color="text.secondary">Lines</Typography>
              </Divider>

              {lines.map((l, i) => (
                <Stack key={i} direction={{ xs: "column", md: "row" }} spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <ProductPicker
                    value={l.product ? Number(l.product) : null}
                    width={230}
                    onChange={(p) => {
                      // v2 §2 pricing master pre-fills the line; still editable
                      setLine(i, {
                        product: p ? String(p.id) : "",
                        units: p?.units ?? [],
                        unit_id: String(p?.units?.find((u) => u.is_base)?.unit_id ?? p?.base_unit_id ?? ""),
                        gst: p?.gst_rate ?? "",
                        hsn: p?.hsn_code ?? "",
                        rate: p?.purchase_price ?? "",
                      });
                      if (p?.price_inclusive) setMny((m) => ({ ...m, price_mode: "inclusive" }));
                    }}
                  />
                  <TextField
                    size="small" label="Unit" select value={l.unit_id} disabled={!l.product}
                    onChange={(e) => setLine(i, { unit_id: e.target.value })} sx={{ width: 100 }}
                  >
                    {l.units.map((u) => (
                      <MenuItem key={u.unit_id} value={String(u.unit_id)}>{u.code}</MenuItem>
                    ))}
                  </TextField>
                  <TextField size="small" label="Godown" select value={l.godown || f.godown}
                    onChange={(e) => setLine(i, { godown: e.target.value })} sx={{ width: 150 }}>
                    {(godowns.data ?? []).map((g) => (
                      <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                    ))}
                  </TextField>
                  <TextField size="small" label="Qty" value={l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} sx={{ width: 85 }} />
                  <TextField size="small" label="Rate" value={l.rate} onChange={(e) => setLine(i, { rate: e.target.value })} sx={{ width: 100 }} />
                  <TextField size="small" label="Disc %" value={l.discount_pct} onChange={(e) => setLine(i, { discount_pct: e.target.value })} sx={{ width: 85 }} />
                  <TextField size="small" label="GST %" value={l.gst} onChange={(e) => setLine(i, { gst: e.target.value })} sx={{ width: 85 }} />
                  <TextField size="small" label="HSN" value={l.hsn} onChange={(e) => setLine(i, { hsn: e.target.value })} sx={{ width: 100 }} />
                  <TextField size="small" label="Remarks" value={l.remarks} onChange={(e) => setLine(i, { remarks: e.target.value })} sx={{ width: 140 }} />
                  <Button
                    size="small" color="inherit"
                    disabled={lines.length === 1}
                    onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}
                  >
                    ✕
                  </Button>
                </Stack>
              ))}
              <Box>
                <Button size="small" onClick={() => setLines((ls) => [...ls, { ...EMPTY_LINE }])}>
                  + Add line
                </Button>
              </Box>

              <Divider textAlign="left">
                <Typography variant="caption" color="text.secondary">Discounts, charges & payment</Typography>
              </Divider>

              <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
                <Box sx={{ flex: 1 }}>
                  <MoneyFields value={mny} onChange={setMny} accounts={accounts.data ?? []} />
                </Box>
                <Box sx={{ p: 2, bgcolor: "#FCFAF6", borderRadius: 1 }}>
                  <MoneyTotalsPanel totals={preview.data?.totals} />
                  <Button
                    type="submit" variant="contained" fullWidth sx={{ mt: 2 }}
                    disabled={create.isPending || !filled.length || !f.supplier}
                  >
                    Post bill
                  </Button>
                </Box>
              </Stack>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Each line receives into its own godown. Posting adds stock at the post-discount
            cost (moving-average), credits the supplier, and pays out anything entered as
            "Paid now" — all in one transaction.
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Recent bills
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Supplier</TableCell>
                <TableCell align="right">Grand total</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Print</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(bills.data ?? []).map((b: PurchaseBill) => (
                <TableRow key={b.id}>
                  <TableCell><code>{b.doc_no}</code></TableCell>
                  <TableCell>{partyName(b.supplier_id)}</TableCell>
                  <TableCell align="right">₹{b.grand_total}</TableCell>
                  <TableCell>{b.status}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => window.open(`/print/purchase_bill/${b.id}`, "_blank")}
                    >
                      Print
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(bills.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography color="text.secondary">No bills yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  );
}
