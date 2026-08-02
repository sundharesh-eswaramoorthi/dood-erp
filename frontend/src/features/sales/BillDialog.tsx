import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import { getOrder } from "./api";

/** v2 §4: the order supplies the lines, this collects the money block and
 *  shows server-computed totals before the invoice is posted. */
export function BillDialog({
  orderId,
  accounts,
  paymentTypes,
  products,
  posting,
  onClose,
  onPost,
}: {
  orderId: number | null;
  accounts: { id: number; name: string }[];
  paymentTypes: { id: number; name: string }[];
  products: { id: number; gst_rate: string | null }[];
  posting: boolean;
  onClose: () => void;
  onPost: (money: Record<string, unknown>, supply: string) => void;
}) {
  const [mny, setMny] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [supply, setSupply] = useState("intra");

  const order = useQuery({
    queryKey: ["sale-order", orderId],
    queryFn: () => getOrder(orderId!),
    enabled: orderId != null,
  });

  const previewLines = (order.data?.lines ?? []).map((l) => ({
    qty: l.entered_qty,
    rate: l.rate,
    gst_rate: products.find((p) => p.id === l.product_id)?.gst_rate ?? "0",
  }));

  const preview = useQuery({
    queryKey: ["money-preview", previewLines, mny, supply],
    queryFn: () => previewMoney(previewLines, mny, supply),
    enabled: previewLines.length > 0,
  });

  return (
    <Dialog open={orderId != null} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Bill order {order.data?.doc_no ?? ""}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              size="small" label="Supply" select value={supply}
              onChange={(e) => setSupply(e.target.value)} sx={{ width: 190 }}
            >
              <MenuItem value="intra">Intra (CGST+SGST)</MenuItem>
              <MenuItem value="inter">Inter (IGST)</MenuItem>
            </TextField>
            <Typography variant="body2" color="text.secondary">
              {previewLines.length} line{previewLines.length === 1 ? "" : "s"} from the order
            </Typography>
          </Stack>
          <Divider />
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
            <Box sx={{ flex: 1 }}>
              <MoneyFields value={mny} onChange={setMny} accounts={accounts}
                paymentTypes={paymentTypes} compact />
            </Box>
            <Box sx={{ p: 2, bgcolor: "#FCFAF6", borderRadius: 1 }}>
              <MoneyTotalsPanel totals={preview.data?.totals} />
            </Box>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={posting || !previewLines.length}
          onClick={() => onPost(moneyPayload(mny), supply)}
        >
          Post bill
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** v2 §3 "Payment history" — what has settled this invoice and what is left. */
