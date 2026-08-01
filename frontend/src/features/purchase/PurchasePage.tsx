import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
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

import { listAccounts } from "../accounts/api";
import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import { listParties } from "../parties/api";
import { listProducts } from "../products/api";
import { getFeatureFlags } from "../settings/api";
import { listGodowns } from "../stock/api";
import { listUnits } from "../units/api";
import {
  cancelOrder,
  createBill,
  createOrder,
  createReturn,
  listBills,
  listOrders,
  receiveOrder,
  type PurchaseBill,
  type PurchaseOrder,
} from "./api";

const EMPTY = { supplier: "", godown: "", supply_type: "intra", product: "", qty: "", rate: "", gst: "" };

/** One editable invoice line (v2 §3: godown, qty, rate, discount, HSN, remarks). */
interface DraftLine {
  product: string;
  godown: string;
  qty: string;
  rate: string;
  gst: string;
  discount_pct: string;
  hsn: string;
  remarks: string;
}

const EMPTY_LINE: DraftLine = {
  product: "", godown: "", qty: "", rate: "", gst: "",
  discount_pct: "", hsn: "", remarks: "",
};

export function PurchasePage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const godowns = useQuery({ queryKey: ["godowns"], queryFn: listGodowns });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const bills = useQuery({ queryKey: ["purchase-bills"], queryFn: listBills });

  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const [f, setF] = useState(EMPTY);
  const [r, setR] = useState(EMPTY);
  const [lines, setLines] = useState<DraftLine[]>([{ ...EMPTY_LINE }]);
  const [mny, setMny] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [msg, setMsg] = useState<string | null>(null);
  const flags = useQuery({ queryKey: ["feature-flags"], queryFn: getFeatureFlags });
  const orders = useQuery({ queryKey: ["purchase-orders"], queryFn: listOrders, enabled: !!flags.data?.purchase_order });

  useEffect(() => {
    if (godowns.data?.length && !f.godown) setF((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (parties.data?.length && !f.supplier) setF((s) => ({ ...s, supplier: String(parties.data![0].id) }));
    if (godowns.data?.length && parties.data?.length && products.data?.length && !r.supplier) {
      const p = products.data![0];
      setR((s) => ({
        ...s,
        supplier: String(parties.data![0].id),
        godown: String(godowns.data![0].id),
        product: String(p.id),
        gst: p.gst_rate ?? "",
      }));
    }
  }, [godowns.data, parties.data, products.data, f.godown, f.supplier, r.supplier]);

  const baseUnitOf = (pid: number) => products.data?.find((p) => p.id === pid)?.base_unit_id ?? 0;
  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  const filled = lines.filter((l) => l.product && l.qty && l.rate);

  // Totals come from the server's money engine so the preview and the posted
  // document can never disagree.
  const preview = useQuery({
    queryKey: ["money-preview", filled, mny, f.supply_type],
    queryFn: () =>
      previewMoney(
        filled.map((l) => ({ qty: l.qty, rate: l.rate, gst_rate: l.gst, discount_pct: l.discount_pct })),
        mny,
        f.supply_type,
      ),
    enabled: filled.length > 0,
  });

  const setLine = (i: number, patch: Partial<DraftLine>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  const create = useMutation({
    mutationFn: () =>
      createBill({
        supplier_id: Number(f.supplier),
        godown_id: Number(f.godown),
        supply_type: f.supply_type,
        ...moneyPayload(mny),
        lines: filled.map((l) => ({
          product_id: Number(l.product),
          godown_id: Number(l.godown || f.godown),
          entered_qty: l.qty,
          entered_unit_id: baseUnitOf(Number(l.product)),
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
      qc.invalidateQueries({ queryKey: ["stock-current"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Bill failed");
    },
  });

  const doReturn = useMutation({
    mutationFn: () =>
      createReturn({
        supplier_id: Number(r.supplier),
        godown_id: Number(r.godown),
        supply_type: r.supply_type,
        lines: [
          { product_id: Number(r.product), entered_qty: r.qty, entered_unit_id: baseUnitOf(Number(r.product)), rate: r.rate, gst_rate: r.gst || undefined },
        ],
      }),
    onSuccess: (b) => {
      setMsg(`Return ${b.doc_no}: ₹${b.grand_total} debited to supplier (payable reduced)`);
      setR({ ...r, qty: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Return failed");
    },
  });

  const [po, setPo] = useState({
    product: "", qty: "", rate: "", gst: "", expected: "", advance: "", account: "",
  });
  const doPO = useMutation({
    mutationFn: () =>
      createOrder({
        supplier_id: Number(r.supplier || f.supplier),
        godown_id: Number(f.godown) || undefined,
        expected_date: po.expected || null,
        advance_amount: po.advance || "0",
        payment_account_id: po.advance ? Number(po.account) || undefined : undefined,
        lines: [{
          product_id: Number(po.product || f.product),
          entered_qty: po.qty,
          entered_unit_id: baseUnitOf(Number(po.product || f.product)),
          rate: po.rate || "0",
          gst_rate: po.gst || undefined,
        }],
      }),
    onSuccess: (o) => {
      setMsg(
        `PO ${o.doc_no} created: ₹${o.grand_total}` +
          (Number(o.advance_amount ?? 0) ? ` · advance ₹${o.advance_amount} paid` : ""),
      );
      setPo({ ...po, product: "", qty: "", rate: "", advance: "" });
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "PO failed");
    },
  });

  // Receiving a PO raises the bill for everything still pending. Over-receipt
  // is warned about, not blocked (decision #10).
  const receivePO = useMutation({
    mutationFn: (id: number) => receiveOrder(id),
    onSuccess: (b) => {
      const warn = b.warnings?.length ? ` — ${b.warnings.join("; ")}` : "";
      setMsg(`Posted ${b.doc_no} against the PO: ₹${b.grand_total}${warn}`);
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
      qc.invalidateQueries({ queryKey: ["purchase-bills"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Receive failed");
    },
  });
  const cancelPO = useMutation({
    mutationFn: (id: number) => cancelOrder(id),
    onSuccess: () => {
      setMsg("Purchase order cancelled");
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Cancel failed");
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Purchase
      </Typography>
      {msg && <Alert severity={msg.startsWith("Posted") ? "success" : "error"}>{msg}</Alert>}

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
                <TextField label="Supply" select value={f.supply_type} onChange={(e) => setF({ ...f, supply_type: e.target.value })} sx={{ width: 170 }}>
                  <MenuItem value="intra">Intra (CGST+SGST)</MenuItem>
                  <MenuItem value="inter">Inter (IGST)</MenuItem>
                </TextField>
              </Stack>

              <Divider textAlign="left">
                <Typography variant="caption" color="text.secondary">Lines</Typography>
              </Divider>

              {lines.map((l, i) => (
                <Stack key={i} direction={{ xs: "column", md: "row" }} spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <TextField
                    size="small" label="Product" select value={l.product}
                    onChange={(e) => {
                      // v2 §2 pricing master pre-fills the line; still editable
                      const p = products.data?.find((pp) => pp.id === Number(e.target.value));
                      setLine(i, {
                        product: e.target.value,
                        gst: p?.gst_rate ?? "",
                        hsn: p?.hsn_code ?? "",
                        rate: p?.purchase_price ?? "",
                      });
                      if (p?.price_inclusive) setMny((m) => ({ ...m, price_mode: "inclusive" }));
                    }}
                    sx={{ flex: 1, minWidth: 180 }}
                  >
                    {(products.data ?? []).map((p) => (
                      <MenuItem key={p.id} value={String(p.id)}>{p.code} · {p.name}</MenuItem>
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
            Purchase return
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (r.supplier && r.godown && r.product && r.qty && r.rate) doReturn.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
              <TextField label="Supplier" select value={r.supplier} onChange={(e) => setR({ ...r, supplier: e.target.value })} sx={{ minWidth: 160 }}>
                {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
              </TextField>
              <TextField label="Godown" select value={r.godown} onChange={(e) => setR({ ...r, godown: e.target.value })} sx={{ width: 150 }}>
                {(godowns.data ?? []).map((g) => (<MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>))}
              </TextField>
              <TextField label="Product" select value={r.product} onChange={(e) => { const gst = products.data?.find((p) => p.id === Number(e.target.value))?.gst_rate ?? ""; setR({ ...r, product: e.target.value, gst }); }} sx={{ minWidth: 160 }}>
                {(products.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>))}
              </TextField>
              <TextField label="Qty" value={r.qty} onChange={(e) => setR({ ...r, qty: e.target.value })} sx={{ width: 90 }} />
              <TextField label="Rate" value={r.rate} onChange={(e) => setR({ ...r, rate: e.target.value })} sx={{ width: 100 }} />
              <TextField label="GST %" value={r.gst} onChange={(e) => setR({ ...r, gst: e.target.value })} sx={{ width: 90 }} />
              <Button type="submit" variant="outlined" color="secondary" sx={{ height: 56 }} disabled={doReturn.isPending}>
                Post return
              </Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Removes stock and debits the supplier's ledger (reduces payable).
          </Typography>
        </CardContent>
      </Card>

      {flags.data?.purchase_order && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Purchase orders <Typography component="span" variant="caption" color="text.secondary">(enabled in Settings)</Typography>
            </Typography>
            <Box
              component="form"
              onSubmit={(e) => {
                e.preventDefault();
                if ((po.product || f.product) && po.qty) doPO.mutate();
              }}
            >
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                <TextField label="Product" select value={po.product || f.product}
                  onChange={(e) => {
                    const p = products.data?.find((pp) => pp.id === Number(e.target.value));
                    setPo({ ...po, product: e.target.value, gst: p?.gst_rate ?? "", rate: p?.purchase_price ?? po.rate });
                  }} sx={{ minWidth: 200 }}>
                  {(products.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>))}
                </TextField>
                <TextField label="Qty" value={po.qty} onChange={(e) => setPo({ ...po, qty: e.target.value })} sx={{ width: 100 }} />
                <TextField label="Rate" value={po.rate} onChange={(e) => setPo({ ...po, rate: e.target.value })} sx={{ width: 110 }} />
                <TextField label="GST %" value={po.gst} onChange={(e) => setPo({ ...po, gst: e.target.value })} sx={{ width: 95 }} />
                <TextField label="Expected" type="date" InputLabelProps={{ shrink: true }}
                  value={po.expected} onChange={(e) => setPo({ ...po, expected: e.target.value })} sx={{ width: 170 }} />
                <TextField label="Advance" value={po.advance}
                  onChange={(e) => setPo({ ...po, advance: e.target.value })} sx={{ width: 110 }}
                  helperText="paid up front" />
                <TextField label="From account" select value={po.account}
                  onChange={(e) => setPo({ ...po, account: e.target.value })}
                  sx={{ width: 170 }} disabled={!po.advance}>
                  {(accounts.data ?? []).map((a) => (<MenuItem key={a.id} value={String(a.id)}>{a.name}</MenuItem>))}
                </TextField>
                <Button type="submit" variant="contained" disabled={doPO.isPending}>Create PO</Button>
              </Stack>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Doc</TableCell>
                  <TableCell>Supplier</TableCell>
                  <TableCell>Expected</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell align="right">Advance</TableCell>
                  <TableCell align="right">Balance</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(orders.data ?? []).map((o: PurchaseOrder) => (
                  <TableRow key={o.id}>
                    <TableCell><code>{o.doc_no}</code></TableCell>
                    <TableCell>{partyName(o.supplier_id)}</TableCell>
                    <TableCell>{o.expected_date || "—"}</TableCell>
                    <TableCell align="right">₹{o.grand_total ?? "0.00"}</TableCell>
                    <TableCell align="right">₹{o.advance_amount ?? "0.00"}</TableCell>
                    <TableCell align="right">₹{o.balance_amount ?? "0.00"}</TableCell>
                    <TableCell>
                      <Chip size="small" label={o.status}
                        color={o.status === "closed" ? "success" : o.status === "cancelled" ? "default" : "warning"} />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" variant="outlined"
                        disabled={receivePO.isPending || o.status === "closed" || o.status === "cancelled"}
                        onClick={() => receivePO.mutate(o.id)}>
                        Receive
                      </Button>
                      <Button size="small" color="inherit"
                        disabled={cancelPO.isPending || o.status === "closed" || o.status === "cancelled"}
                        onClick={() => cancelPO.mutate(o.id)}>
                        Cancel
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(orders.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography color="text.secondary">No purchase orders yet.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <Typography variant="caption" color="text.secondary">
              "Receive" raises the purchase bill for everything still pending and moves the stock.
              Receiving more than ordered is allowed but warns (tolerance is a setting).
            </Typography>
          </CardContent>
        </Card>
      )}

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
