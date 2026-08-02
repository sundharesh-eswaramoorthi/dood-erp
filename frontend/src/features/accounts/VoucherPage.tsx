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

import { errorMessage } from "../../lib/api";
import { usableSplits, type PaymentSplit } from "../money/api";
import { PaymentSplits } from "../money/MoneyBlock";
import { listParties } from "../parties/api";
import {
  listAccounts,
  listOpenItems,
  listPaymentTypes,
  listVouchers,
  postVoucher,
  type OpenItem,
  type Voucher,
} from "./api";

/** Money in and money out are the same document with the sign flipped, so one
 *  component serves both rather than two that drift apart. */
export function VoucherPage({ kind }: { kind: "receipt" | "payment" }) {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const vouchers = useQuery({ queryKey: ["vouchers"], queryFn: listVouchers });
  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const [party, setParty] = useState("");
  const [note, setNote] = useState("");
  const [splits, setSplits] = useState<PaymentSplit[]>([]);
  // v2 §3: which bills this settles. Empty selection = oldest first (FIFO).
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const receipt = kind === "receipt";
  const title = receipt ? "Payment in" : "Payment out";

  useEffect(() => {
    if (parties.data?.length && !party) setParty(String(parties.data[0].id));
  }, [parties.data, party]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;
  const accName = (id: number) => accounts.data?.find((a) => a.id === id)?.name ?? id;

  // What this party still owes, bill by bill — a receipt settles a debit,
  // a payment settles a credit.
  const openItems = useQuery({
    queryKey: ["open-items", party, kind],
    queryFn: () => listOpenItems(Number(party), receipt ? "debit" : "credit"),
    enabled: !!party,
  });

  const post = useMutation({
    mutationFn: () => {
      const chosen = Object.entries(picked)
        .filter(([, amt]) => amt && Number(amt) > 0)
        .map(([entry, amt]) => ({ against_entry_id: Number(entry), amount: amt }));
      return postVoucher({
        party_id: Number(party),
        voucher_type: kind,
        note,
        // the server derives the amount and header account from the tenders
        payments: usableSplits(splits).map((p) => ({
          account_id: p.account_id as number,
          payment_type_id: p.payment_type_id ?? undefined,
          amount: p.amount,
          reference: p.reference || undefined,
        })),
        // omit entirely to let the server settle the oldest bills first
        ...(chosen.length ? { allocations: chosen } : {}),
      });
    },
    onSuccess: (r) => {
      const applied = r.allocations?.length
        ? ` Settled ${r.allocations.length} bill(s)` +
          (Number(r.unallocated) ? `, ₹${r.unallocated} left on account.` : ".")
        : "";
      setMsg({
        text: `${r.doc_no}: account balance ₹${r.account_balance}, party net ₹${r.party_net}.${applied}`,
        ok: true,
      });
      setNote("");
      setSplits([]);
      setPicked({});
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["vouchers"] });
      qc.invalidateQueries({ queryKey: ["open-items"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, `Could not post the ${title.toLowerCase()}`), ok: false }),
  });

  const rows = (vouchers.data ?? []).filter((x: Voucher) => x.voucher_type === kind);

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>{title}</Typography>
        <Typography color="text.secondary">
          {receipt
            ? "A customer pays us: the party's receivable falls and the money lands in an account."
            : "We pay a supplier: the party's payable falls and the money leaves an account."}
        </Typography>
      </Box>
      {msg && (
        <Alert severity={msg.ok ? "success" : "error"} onClose={() => setMsg(null)}>{msg.text}</Alert>
      )}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Record {receipt ? "a receipt" : "a payment"}
          </Typography>
          <Box component="form"
            onSubmit={(e) => { e.preventDefault(); if (party && usableSplits(splits).length) post.mutate(); }}>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                <TextField label="Party" select value={party}
                  onChange={(e) => setParty(e.target.value)} sx={{ minWidth: 220 }}>
                  {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
                </TextField>
                <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)}
                  sx={{ flex: 1, minWidth: 200 }} />
                <Button type="submit" variant="contained" disabled={post.isPending}>Post</Button>
              </Stack>

              {/* v2 §3: one receipt can arrive part cash, part UPI */}
              <PaymentSplits
                value={splits}
                onChange={setSplits}
                accounts={accounts.data ?? []}
                paymentTypes={paymentTypes.data ?? []}
                label={receipt ? "Received" : "Paid"}
              />

              {(openItems.data ?? []).length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Settle against {receipt ? "these bills" : "these payables"}
                    <Typography component="span" variant="caption" color="text.secondary">
                      {" "}— leave blank to settle the oldest first
                    </Typography>
                  </Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Document</TableCell>
                        <TableCell>Date</TableCell>
                        <TableCell align="right">Amount</TableCell>
                        <TableCell align="right">Outstanding</TableCell>
                        <TableCell align="right" sx={{ width: 150 }}>Settle</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(openItems.data ?? []).map((it: OpenItem) => (
                        <TableRow key={it.entry_id}>
                          <TableCell>{it.source_doc_type.replace(/_/g, " ")} #{it.source_doc_id}</TableCell>
                          <TableCell>{it.effective_date}</TableCell>
                          <TableCell align="right">₹{it.amount}</TableCell>
                          <TableCell align="right"><strong>₹{it.outstanding}</strong></TableCell>
                          <TableCell align="right">
                            <TextField size="small" placeholder="0.00"
                              value={picked[it.entry_id] ?? ""}
                              onChange={(e) => setPicked({ ...picked, [it.entry_id]: e.target.value })}
                              sx={{ width: 130 }} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>{title} history</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Party</TableCell>
                <TableCell>Account</TableCell>
                <TableCell align="right">Amount</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((x: Voucher) => (
                <TableRow key={x.id}>
                  <TableCell><code>{x.doc_no}</code></TableCell>
                  <TableCell>{partyName(x.party_id)}</TableCell>
                  <TableCell>{accName(x.account_id)}</TableCell>
                  <TableCell align="right">₹{x.amount}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography color="text.secondary">Nothing recorded yet.</Typography>
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

export const PaymentInPage = () => <VoucherPage kind="receipt" />;
export const PaymentOutPage = () => <VoucherPage kind="payment" />;
