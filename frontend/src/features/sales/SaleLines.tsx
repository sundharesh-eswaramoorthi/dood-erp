import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Button,
  IconButton,
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

import { ProductPicker } from "../../components/ProductPicker";
import type { Product } from "../products/api";
import type { Godown } from "../stock/api";

/** One editable invoice line. Everything is a string: these are form fields,
 *  and the server does the arithmetic. */
export interface SaleLine {
  key: number;
  product: Product | null;
  unit_id: string;
  qty: string;
  rate: string;
  gst: string;
  discount_pct: string;
  godown_id: string;
}

let nextKey = 1;

export function emptyLine(godownId = ""): SaleLine {
  return {
    key: nextKey++,
    product: null,
    unit_id: "",
    qty: "",
    rate: "",
    gst: "",
    discount_pct: "",
    godown_id: godownId,
  };
}

/** A line is worth posting once it names a product, a quantity and a place. */
export function isComplete(l: SaleLine): boolean {
  return !!(l.product && Number(l.qty) > 0 && l.godown_id && l.unit_id);
}

export function toPayload(lines: SaleLine[]) {
  return lines.filter(isComplete).map((l) => ({
    product_id: l.product!.id,
    godown_id: Number(l.godown_id),
    entered_qty: l.qty,
    entered_unit_id: Number(l.unit_id),
    rate: l.rate || "0",
    gst_rate: l.gst || undefined,
    discount_pct: l.discount_pct || undefined,
  }));
}

/** What the money preview needs: quantity, rate and tax per line. */
export function toPreviewLines(lines: SaleLine[]) {
  return lines.filter(isComplete).map((l) => ({
    qty: l.qty,
    rate: l.rate || "0",
    gst_rate: l.gst || "0",
    discount_pct: l.discount_pct || "0",
  }));
}

export function SaleLinesEditor({
  lines,
  onChange,
  godowns,
  onPriceModeHint,
}: {
  lines: SaleLine[];
  onChange: (lines: SaleLine[]) => void;
  /** already narrowed to the document's branch */
  godowns: Godown[];
  /** fired when a picked product is priced inclusive of tax */
  onPriceModeHint?: (inclusive: boolean) => void;
}) {
  const patch = (key: number, changes: Partial<SaleLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...changes } : l)));

  const pickProduct = (l: SaleLine, p: Product | null) => {
    if (!p) return patch(l.key, { product: null, unit_id: "" });
    // Everything the master already knows, filled in: rate, tax and the unit.
    // Leaving these blank is how an order ends up quoted at 0% GST.
    const base = p.units?.find((u) => u.is_base);
    patch(l.key, {
      product: p,
      unit_id: String(base?.unit_id ?? p.base_unit_id),
      rate: p.sale_price ?? l.rate,
      gst: p.gst_rate ?? "",
    });
    if (p.price_inclusive) onPriceModeHint?.(true);
  };

  const add = () => onChange([...lines, emptyLine(godowns[0] ? String(godowns[0].id) : "")]);
  const remove = (key: number) => onChange(lines.filter((l) => l.key !== key));

  return (
    <Stack spacing={1}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ minWidth: 260 }}>Product</TableCell>
            <TableCell sx={{ width: 110 }}>Unit</TableCell>
            <TableCell sx={{ width: 90 }}>Qty</TableCell>
            <TableCell sx={{ width: 110 }}>Rate</TableCell>
            <TableCell sx={{ width: 85 }}>Disc %</TableCell>
            <TableCell sx={{ width: 85 }}>GST %</TableCell>
            <TableCell sx={{ width: 150 }}>Godown</TableCell>
            <TableCell sx={{ width: 100 }} align="right">Amount</TableCell>
            <TableCell sx={{ width: 44 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {lines.map((l) => {
            const units = l.product?.units ?? [];
            const gross = Number(l.qty || 0) * Number(l.rate || 0);
            const net = gross * (1 - Number(l.discount_pct || 0) / 100);
            return (
              <TableRow key={l.key}>
                <TableCell>
                  <ProductPicker
                    value={l.product?.id ?? null}
                    onChange={(p) => pickProduct(l, p)}
                    label=""
                    width="100%"
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small" select value={l.unit_id} fullWidth
                    onChange={(e) => patch(l.key, { unit_id: e.target.value })}
                    disabled={!l.product}
                  >
                    {units.map((u) => (
                      <MenuItem key={u.unit_id} value={String(u.unit_id)}>{u.code}</MenuItem>
                    ))}
                  </TextField>
                </TableCell>
                <TableCell>
                  <TextField size="small" value={l.qty} fullWidth
                    onChange={(e) => patch(l.key, { qty: e.target.value })} />
                </TableCell>
                <TableCell>
                  <TextField size="small" value={l.rate} fullWidth
                    onChange={(e) => patch(l.key, { rate: e.target.value })} />
                </TableCell>
                <TableCell>
                  <TextField size="small" value={l.discount_pct} fullWidth
                    onChange={(e) => patch(l.key, { discount_pct: e.target.value })} />
                </TableCell>
                <TableCell>
                  <TextField size="small" value={l.gst} fullWidth
                    onChange={(e) => patch(l.key, { gst: e.target.value })} />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small" select value={l.godown_id} fullWidth
                    onChange={(e) => patch(l.key, { godown_id: e.target.value })}
                  >
                    {godowns.map((g) => (
                      <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                    ))}
                  </TextField>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    {net ? `₹${net.toFixed(2)}` : "—"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <IconButton
                    size="small"
                    onClick={() => remove(l.key)}
                    disabled={lines.length === 1}
                    title={lines.length === 1 ? "a document needs at least one line" : "remove line"}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <Stack direction="row" spacing={2} alignItems="center">
        <Button size="small" onClick={add}>+ Add line</Button>
        <Typography variant="caption" color="text.secondary">
          Each line carries its own godown, so one invoice can ship from several.
          Amounts here are before overall discount and tax.
        </Typography>
      </Stack>
    </Stack>
  );
}
