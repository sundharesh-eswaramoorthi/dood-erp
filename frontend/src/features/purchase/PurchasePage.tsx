import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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

import { listParties } from "../parties/api";
import { listProducts } from "../products/api";
import { getFeatureFlags } from "../settings/api";
import { listGodowns } from "../stock/api";
import { listUnits } from "../units/api";
import {
  createBill,
  createOrder,
  createReturn,
  listBills,
  listOrders,
  type PurchaseBill,
  type PurchaseOrder,
} from "./api";

const EMPTY = { supplier: "", godown: "", supply_type: "intra", product: "", qty: "", rate: "", gst: "" };

export function PurchasePage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const godowns = useQuery({ queryKey: ["godowns"], queryFn: listGodowns });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const bills = useQuery({ queryKey: ["purchase-bills"], queryFn: listBills });

  const [f, setF] = useState(EMPTY);
  const [r, setR] = useState(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const flags = useQuery({ queryKey: ["feature-flags"], queryFn: getFeatureFlags });
  const orders = useQuery({ queryKey: ["purchase-orders"], queryFn: listOrders, enabled: !!flags.data?.purchase_order });

  useEffect(() => {
    if (godowns.data?.length && !f.godown) setF((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (parties.data?.length && !f.supplier) setF((s) => ({ ...s, supplier: String(parties.data![0].id) }));
    if (products.data?.length && !f.product) {
      const p = products.data![0];
      setF((s) => ({ ...s, product: String(p.id), gst: p.gst_rate ?? "" }));
    }
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
  }, [godowns.data, parties.data, products.data, f.godown, f.supplier, f.product, r.supplier]);

  const baseUnitOf = (pid: number) => products.data?.find((p) => p.id === pid)?.base_unit_id ?? 0;
  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  const create = useMutation({
    mutationFn: () =>
      createBill({
        supplier_id: Number(f.supplier),
        godown_id: Number(f.godown),
        supply_type: f.supply_type,
        lines: [
          {
            product_id: Number(f.product),
            entered_qty: f.qty,
            entered_unit_id: baseUnitOf(Number(f.product)),
            rate: f.rate,
            gst_rate: f.gst || undefined,
          },
        ],
      }),
    onSuccess: (b) => {
      setMsg(`Posted ${b.doc_no}: grand total ₹${b.grand_total} (tax ₹${b.tax_total}) → supplier payable`);
      setF({ ...f, qty: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["purchase-bills"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Bill failed");
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

  const [po, setPo] = useState({ product: "", qty: "", rate: "" });
  const doPO = useMutation({
    mutationFn: () =>
      createOrder({
        supplier_id: Number(r.supplier || f.supplier),
        lines: [{ product_id: Number(po.product || f.product), entered_qty: po.qty, entered_unit_id: baseUnitOf(Number(po.product || f.product)), rate: po.rate || "0" }],
      }),
    onSuccess: (o) => {
      setMsg(`PO ${o.doc_no} created`);
      setPo({ product: "", qty: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
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
              if (f.supplier && f.godown && f.product && f.qty && f.rate) create.mutate();
            }}
          >
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField label="Supplier" select value={f.supplier} onChange={(e) => setF({ ...f, supplier: e.target.value })} sx={{ flex: 1, minWidth: 180 }}>
                  {(parties.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Godown" select value={f.godown} onChange={(e) => setF({ ...f, godown: e.target.value })} sx={{ width: 170 }}>
                  {(godowns.data ?? []).map((g) => (
                    <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Supply" select value={f.supply_type} onChange={(e) => setF({ ...f, supply_type: e.target.value })} sx={{ width: 150 }}>
                  <MenuItem value="intra">Intra (CGST+SGST)</MenuItem>
                  <MenuItem value="inter">Inter (IGST)</MenuItem>
                </TextField>
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
                <TextField label="Product" select value={f.product} onChange={(e) => { const gst = products.data?.find((p) => p.id === Number(e.target.value))?.gst_rate ?? ""; setF({ ...f, product: e.target.value, gst }); }} sx={{ flex: 1, minWidth: 200 }}>
                  {(products.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>{p.code} · {p.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Qty" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} sx={{ width: 100 }} />
                <TextField label="Rate" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} sx={{ width: 120 }} />
                <TextField label="GST %" value={f.gst} onChange={(e) => setF({ ...f, gst: e.target.value })} sx={{ width: 100 }} />
                <Button type="submit" variant="contained" sx={{ height: 56 }} disabled={create.isPending}>
                  Post bill
                </Button>
              </Stack>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Posting adds stock (moving-average) and credits the supplier's ledger (payable) in one transaction.
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
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                <TextField label="Product" select value={po.product || f.product} onChange={(e) => setPo({ ...po, product: e.target.value })} sx={{ minWidth: 200 }}>
                  {(products.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>))}
                </TextField>
                <TextField label="Qty" value={po.qty} onChange={(e) => setPo({ ...po, qty: e.target.value })} sx={{ width: 100 }} />
                <TextField label="Rate" value={po.rate} onChange={(e) => setPo({ ...po, rate: e.target.value })} sx={{ width: 100 }} />
                <Button type="submit" variant="contained" disabled={doPO.isPending}>Create PO</Button>
              </Stack>
            </Box>
            <Stack spacing={0.5}>
              {(orders.data ?? []).map((o: PurchaseOrder) => (
                <Typography key={o.id} variant="body2">
                  <code>{o.doc_no}</code> · {partyName(o.supplier_id)} · {o.status}
                </Typography>
              ))}
            </Stack>
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
              </TableRow>
            </TableHead>
            <TableBody>
              {(bills.data ?? []).map((b: PurchaseBill) => (
                <TableRow key={b.id}>
                  <TableCell><code>{b.doc_no}</code></TableCell>
                  <TableCell>{partyName(b.supplier_id)}</TableCell>
                  <TableCell align="right">₹{b.grand_total}</TableCell>
                  <TableCell>{b.status}</TableCell>
                </TableRow>
              ))}
              {(bills.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
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
