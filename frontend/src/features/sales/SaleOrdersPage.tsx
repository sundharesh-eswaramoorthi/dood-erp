import {
  Alert,
  Box,
  Button,
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessage } from "../../lib/api";
import { cancelOrder, createOrder, deliverOrder, listOrders, type SaleOrder } from "./api";
import { SaleDocumentCard } from "./SaleDocumentCard";
import { useSalesHeader } from "./useSalesHeader";
import { invalidateStock } from "../../app/refresh";

const STATUS_COLOR: Record<string, "warning" | "success" | "default"> = {
  pending: "warning",
  delivered: "success",
  cancelled: "default",
};

type Note = { text: string; severity: "success" | "error" | "warning" };

export function SaleOrdersPage() {
  const qc = useQueryClient();
  const h = useSalesHeader();
  const orders = useQuery({ queryKey: [...["sale-orders"], h.branchId], queryFn: () => listOrders(h.branchId) });
  const [note, setNote] = useState<Note | null>(null);

  const fail = (e: unknown, fallback: string) =>
    setNote({ text: errorMessage(e, fallback), severity: "error" });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelOrder(id),
    onSuccess: () => {
      setNote({ text: "Order cancelled — reservation released.", severity: "success" });
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      invalidateStock(qc);
    },
    onError: (e) => fail(e, "Could not cancel the order"),
  });

  const deliver = useMutation({
    mutationFn: (id: number) => deliverOrder(id),
    onSuccess: (d) => {
      setNote({
        text: `Dispatched ${d.doc_no} — stock moved once, reservation released, order delivered.`,
        severity: "success",
      });
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      invalidateStock(qc);
    },
    onError: (e) => fail(e, "Could not dispatch the delivery"),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Sale orders</Typography>
        <Typography color="text.secondary">
          An order reserves stock — nothing leaves the godown until it is delivered or billed.
        </Typography>
      </Box>
      {note && <Alert severity={note.severity} onClose={() => setNote(null)}>{note.text}</Alert>}

      <SaleDocumentCard
        title="New sale order"
        subtitle="reserves stock — nothing moves until delivery"
        actionLabel="Place order"
        customer={h.customer}
        onCustomer={h.setCustomer}
        branch={h.branch}
        onBranch={h.setBranch}
        parties={h.parties}
        branches={h.branches}
        godowns={h.godowns}
        accounts={h.accounts}
        paymentTypes={h.paymentTypes}
        showMoney={false}
        onSubmit={async (payload) => {
          const o = await createOrder(payload as Parameters<typeof createOrder>[0]);
          setNote({
            text:
              `Order ${o.doc_no} placed — stock reserved.` +
              (o.credit_warning ? ` ${o.credit_warning}` : ""),
            severity: o.credit_warning ? "warning" : "success",
          });
          qc.invalidateQueries({ queryKey: ["sale-orders"] });
          invalidateStock(qc);
        }}
        onError={(e) => fail(e, "Could not place the order")}
      />

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Orders</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {(orders.data ?? []).map((o: SaleOrder) => (
                <TableRow key={o.id}>
                  <TableCell><code>{o.doc_no}</code></TableCell>
                  <TableCell>{h.partyName(o.customer_id)}</TableCell>
                  <TableCell>
                    <Chip size="small" label={o.status} color={STATUS_COLOR[o.status] ?? "default"} />
                  </TableCell>
                  <TableCell align="right">
                    {o.status === "pending" && (
                      <>
                        <Button size="small" onClick={() => deliver.mutate(o.id)} disabled={deliver.isPending}>
                          Deliver
                        </Button>
                        <Button size="small" color="secondary" onClick={() => cancel.mutate(o.id)}
                          disabled={cancel.isPending}>
                          Cancel
                        </Button>
                      </>
                    )}
                    {o.status === "delivered" && (
                      <Typography variant="caption" color="text.secondary">
                        bill it from Sales invoices
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(orders.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography color="text.secondary">No orders yet.</Typography>
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
