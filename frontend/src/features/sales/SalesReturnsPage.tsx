import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessage } from "../../lib/api";
import { createReturn, listReturns, type SalesReturn } from "./api";
import { SaleDocumentCard } from "./SaleDocumentCard";
import { useSalesHeader } from "./useSalesHeader";

type Note = { text: string; severity: "success" | "error" };

/** v2 §4 credit note. The endpoint has existed since Phase 4c; until now there
 *  was no screen for it, so goods coming back had to be entered through the API
 *  or not at all. */
export function SalesReturnsPage() {
  const qc = useQueryClient();
  const h = useSalesHeader();
  const returns = useQuery({ queryKey: ["sales-returns"], queryFn: listReturns });
  const [note, setNote] = useState<Note | null>(null);

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Sales returns</Typography>
        <Typography color="text.secondary">
          A credit note: the goods come back into a godown and the customer's account is
          credited. Money refunded now goes on the payment lines.
        </Typography>
      </Box>
      {note && <Alert severity={note.severity} onClose={() => setNote(null)}>{note.text}</Alert>}

      <SaleDocumentCard
        title="New sales return"
        subtitle="goods back in, customer credited"
        actionLabel="Post return"
        customer={h.customer}
        onCustomer={h.setCustomer}
        branch={h.branch}
        onBranch={h.setBranch}
        parties={h.parties}
        branches={h.branches}
        godowns={h.godowns}
        accounts={h.accounts}
        paymentTypes={h.paymentTypes}
        showMoney
        onSubmit={async (payload) => {
          const r = await createReturn(payload as Parameters<typeof createReturn>[0]);
          setNote({
            text: `Credit note ${r.doc_no}: ₹${r.grand_total} credited to ${h.partyName(
              Number(payload.customer_id),
            )}. Stock is back in the godown.`,
            severity: "success",
          });
          qc.invalidateQueries({ queryKey: ["sales-returns"] });
          qc.invalidateQueries({ queryKey: ["stock-current"] });
          qc.invalidateQueries({ queryKey: ["accounts"] });
        }}
        onError={(e) => setNote({ text: errorMessage(e, "Could not post the return"), severity: "error" })}
      />

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Credit notes</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Against</TableCell>
                <TableCell>Date</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {(returns.data ?? []).map((r: SalesReturn) => (
                <TableRow key={r.id} sx={{ opacity: r.status === "cancelled" ? 0.5 : 1 }}>
                  <TableCell>
                    <code>{r.doc_no}</code>
                    {r.status === "cancelled" && <Chip size="small" label="cancelled" sx={{ ml: 0.5 }} />}
                  </TableCell>
                  <TableCell>{h.partyName(r.customer_id)}</TableCell>
                  <TableCell>{r.orig_bill_id ? `Invoice #${r.orig_bill_id}` : "—"}</TableCell>
                  <TableCell>{r.return_date ?? "—"}</TableCell>
                  <TableCell align="right">₹{r.grand_total}</TableCell>
                  <TableCell align="right">
                    <Box
                      component="button"
                      type="button"
                      onClick={() => window.open(`/print/sales_return/${r.id}`, "_blank")}
                      sx={{
                        border: 0, background: "none", cursor: "pointer",
                        color: "primary.main", font: "inherit", p: 0,
                      }}
                    >
                      Print
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
              {(returns.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No credit notes yet.</Typography>
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
