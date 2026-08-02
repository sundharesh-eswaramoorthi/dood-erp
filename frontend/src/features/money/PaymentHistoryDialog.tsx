import {
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { billPayments } from "../accounts/api";

/** v2 §3 "Payment history" — what has settled this invoice and what is left. */
export function PaymentHistoryDialog({
  billId,
  kind = "sales",
  onClose,
}: {
  billId: number | null;
  /** which side of the ledger the document sits on */
  kind?: "sales" | "purchase";
  onClose: () => void;
}) {
  const history = useQuery({
    queryKey: ["bill-payments", kind, billId],
    queryFn: () => billPayments(kind, billId!),
    enabled: billId != null,
  });
  const h = history.data;

  return (
    <Dialog open={billId != null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Payment history</DialogTitle>
      <DialogContent>
        {h ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <Chip label={`Invoice ₹${h.invoice_total}`} />
              <Chip color="success" label={`Settled ₹${h.settled}`} />
              <Chip color={Number(h.outstanding) > 0 ? "error" : "default"}
                label={`Outstanding ₹${h.outstanding}`} />
            </Stack>
            <Divider />
            {h.payments.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Nothing has been settled against this invoice yet.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell align="right">Amount</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {h.payments.map((p, i) => (
                    <TableRow key={i}>
                      <TableCell>{p.effective_date}</TableCell>
                      <TableCell>
                        {p.doc_no ?? p.source_doc_type.replace(/_/g, " ")}
                      </TableCell>
                      <TableCell>{p.payment_type ?? "—"}</TableCell>
                      <TableCell align="right">₹{p.amount}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Stack>
        ) : (
          <Typography color="text.secondary">Loading…</Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
