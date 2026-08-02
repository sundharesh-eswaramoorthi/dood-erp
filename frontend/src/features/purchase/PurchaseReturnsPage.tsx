import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
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
import { listParties } from "../parties/api";
import { listGodowns } from "../stock/api";
import { createReturn, listReturns, type PurchaseReturnRow } from "./api";

const EMPTY = { supplier: "", godown: "", supply_type: "intra", product: "", qty: "", rate: "", gst: "", unit_id: "" };

/** v2 §3 debit note: goods go back to the supplier and the payable falls. */
export function PurchaseReturnsPage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const godowns = useQuery({ queryKey: ["godowns"], queryFn: () => listGodowns() });
  const returns = useQuery({ queryKey: ["purchase-returns"], queryFn: listReturns });

  const [r, setR] = useState(EMPTY);
  const [unitId, setUnitId] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (godowns.data?.length && !r.godown) setR((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (parties.data?.length && !r.supplier) setR((s) => ({ ...s, supplier: String(parties.data![0].id) }));
  }, [godowns.data, parties.data, r.godown, r.supplier]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  const doReturn = useMutation({
    mutationFn: () =>
      createReturn({
        supplier_id: Number(r.supplier),
        godown_id: Number(r.godown),
        supply_type: r.supply_type,
        lines: [
          { product_id: Number(r.product), entered_qty: r.qty, entered_unit_id: unitId ?? 0,
            rate: r.rate, gst_rate: r.gst || undefined },
        ],
      }),
    onSuccess: (b) => {
      setMsg(`Return ${b.doc_no}: ₹${b.grand_total} debited to the supplier (payable reduced)`);
      setR({ ...r, qty: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["purchase-returns"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => setMsg(errorMessage(e, "Return failed")),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Purchase returns</Typography>
        <Typography color="text.secondary">
          A debit note: stock leaves the godown and the supplier's payable falls.
        </Typography>
      </Box>
      {msg && (
        <Alert severity={msg.startsWith("Return") ? "success" : "error"} onClose={() => setMsg(null)}>
          {msg}
        </Alert>
      )}

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
              <ProductPicker
                value={r.product ? Number(r.product) : null}
                size="medium"
                width={230}
                onChange={(p) => {
                  setR({ ...r, product: p ? String(p.id) : "", gst: p?.gst_rate ?? "" });
                  setUnitId(p?.units?.find((u) => u.is_base)?.unit_id ?? p?.base_unit_id ?? null);
                }}
              />
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
    </Stack>
  );
}
