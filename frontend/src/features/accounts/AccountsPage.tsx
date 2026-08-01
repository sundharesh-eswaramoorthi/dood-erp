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

import { listParties } from "../parties/api";
import {
  createAccount,
  createPaymentType,
  listAccounts,
  listOpenItems,
  listPaymentTypes,
  listExpenseCategories,
  listExpenses,
  listVouchers,
  postExpense,
  postVoucher,
  type Account,
  type Expense,
  type OpenItem,
  type Voucher,
} from "./api";

export function AccountsPage() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const vouchers = useQuery({ queryKey: ["vouchers"], queryFn: listVouchers });

  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });
  const categories = useQuery({ queryKey: ["expense-categories"], queryFn: listExpenseCategories });
  const expenses = useQuery({ queryKey: ["expenses"], queryFn: listExpenses });

  const [acc, setAcc] = useState({ name: "", account_type: "bank", opening: "0" });
  const [v, setV] = useState({ party: "", account: "", type: "receipt", amount: "", note: "", payment_type: "" });
  // v2 §3: which bills this settles. Empty selection = oldest first (FIFO).
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [newPayType, setNewPayType] = useState("");
  const [ex, setEx] = useState({ account: "", category: "", amount: "", note: "" });
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (parties.data?.length && !v.party) setV((s) => ({ ...s, party: String(parties.data![0].id) }));
    if (accounts.data?.length && !v.account) setV((s) => ({ ...s, account: String(accounts.data![0].id) }));
    if (accounts.data?.length && !ex.account) setEx((s) => ({ ...s, account: String(accounts.data![0].id) }));
    if (categories.data?.length && !ex.category) setEx((s) => ({ ...s, category: String(categories.data![0].id) }));
  }, [parties.data, accounts.data, categories.data, v.party, v.account, ex.account, ex.category]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;
  const accName = (id: number) => accounts.data?.find((a) => a.id === id)?.name ?? id;

  const addAcc = useMutation({
    mutationFn: () => createAccount({ name: acc.name, account_type: acc.account_type, opening_balance: acc.opening || "0" }),
    onSuccess: () => {
      setAcc({ name: "", account_type: "bank", opening: "0" });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  // What this party still owes, bill by bill — a receipt settles a debit,
  // a payment settles a credit.
  const openItems = useQuery({
    queryKey: ["open-items", v.party, v.type],
    queryFn: () => listOpenItems(Number(v.party), v.type === "receipt" ? "debit" : "credit"),
    enabled: !!v.party,
  });

  const addPayType = useMutation({
    mutationFn: () => createPaymentType({ name: newPayType }),
    onSuccess: () => {
      setNewPayType("");
      qc.invalidateQueries({ queryKey: ["payment-types"] });
    },
  });

  const pay = useMutation({
    mutationFn: () => {
      const chosen = Object.entries(picked)
        .filter(([, amt]) => amt && Number(amt) > 0)
        .map(([entry, amt]) => ({ against_entry_id: Number(entry), amount: amt }));
      return postVoucher({
        party_id: Number(v.party),
        account_id: Number(v.account),
        voucher_type: v.type,
        amount: v.amount,
        note: v.note,
        payment_type_id: v.payment_type ? Number(v.payment_type) : undefined,
        // omit entirely to let the server settle the oldest bills first
        ...(chosen.length ? { allocations: chosen } : {}),
      });
    },
    onSuccess: (r) => {
      const applied = r.allocations?.length
        ? ` Settled ${r.allocations.length} bill(s)` +
          (Number(r.unallocated) ? `, ₹${r.unallocated} left on account.` : ".")
        : "";
      setMsg(`${r.doc_no}: account balance ₹${r.account_balance}, party net ₹${r.party_net}.${applied}`);
      setV({ ...v, amount: "", note: "" });
      setPicked({});
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["vouchers"] });
      qc.invalidateQueries({ queryKey: ["open-items"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Voucher failed");
    },
  });

  const addExpense = useMutation({
    mutationFn: () =>
      postExpense({ account_id: Number(ex.account), amount: ex.amount, category_id: ex.category ? Number(ex.category) : null, note: ex.note }),
    onSuccess: (r) => {
      setMsg(`Expense ${r.doc_no}: account balance ₹${r.account_balance}.`);
      setEx({ ...ex, amount: "", note: "" });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["expenses"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Expense failed");
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Accounts &amp; Payments
      </Typography>
      {msg && <Alert severity={msg.includes("failed") ? "error" : "success"}>{msg}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Cash / bank accounts
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
            {(accounts.data ?? []).map((a: Account) => (
              <Chip key={a.id} label={`${a.name}: ₹${a.current_balance}`} color={a.account_type === "bank" ? "primary" : "default"} />
            ))}
          </Stack>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (acc.name) addAcc.mutate(); }}>
            <Stack direction="row" spacing={2}>
              <TextField size="small" label="Name" value={acc.name} onChange={(e) => setAcc({ ...acc, name: e.target.value })} />
              <TextField size="small" label="Type" select value={acc.account_type} onChange={(e) => setAcc({ ...acc, account_type: e.target.value })} sx={{ width: 140 }}>
                <MenuItem value="bank">Bank</MenuItem>
                <MenuItem value="cash">Cash</MenuItem>
                <MenuItem value="petty_cash">Petty cash</MenuItem>
              </TextField>
              <TextField size="small" label="Opening" value={acc.opening} onChange={(e) => setAcc({ ...acc, opening: e.target.value })} sx={{ width: 120 }} />
              <Button type="submit" variant="outlined" disabled={addAcc.isPending}>Add account</Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Record receipt / payment
          </Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (v.party && v.account && v.amount) pay.mutate(); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField label="Type" select value={v.type} onChange={(e) => setV({ ...v, type: e.target.value })} sx={{ width: 160 }}>
                <MenuItem value="receipt">Receipt (money in)</MenuItem>
                <MenuItem value="payment">Payment (money out)</MenuItem>
              </TextField>
              <TextField label="Party" select value={v.party} onChange={(e) => setV({ ...v, party: e.target.value })} sx={{ minWidth: 180 }}>
                {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
              </TextField>
              <TextField label="Account" select value={v.account} onChange={(e) => setV({ ...v, account: e.target.value })} sx={{ minWidth: 160 }}>
                {(accounts.data ?? []).map((a) => (<MenuItem key={a.id} value={String(a.id)}>{a.name}</MenuItem>))}
              </TextField>
              <TextField label="Amount" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} sx={{ width: 120 }} />
              <TextField label="Payment type" select value={v.payment_type}
                onChange={(e) => setV({ ...v, payment_type: e.target.value })} sx={{ minWidth: 150 }}>
                <MenuItem value=""><em>Unspecified</em></MenuItem>
                {(paymentTypes.data ?? []).map((t) => (<MenuItem key={t.id} value={String(t.id)}>{t.name}</MenuItem>))}
              </TextField>
              <TextField label="Note" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} />
              <Button type="submit" variant="contained" disabled={pay.isPending}>Post</Button>
            </Stack>

            {(openItems.data ?? []).length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Settle against {v.type === "receipt" ? "these bills" : "these payables"}
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
                        <TableCell>
                          {it.source_doc_type.replace(/_/g, " ")} #{it.source_doc_id}
                        </TableCell>
                        <TableCell>{it.effective_date}</TableCell>
                        <TableCell align="right">₹{it.amount}</TableCell>
                        <TableCell align="right"><strong>₹{it.outstanding}</strong></TableCell>
                        <TableCell align="right">
                          <TextField
                            size="small" placeholder="0.00"
                            value={picked[it.entry_id] ?? ""}
                            onChange={(e) => setPicked({ ...picked, [it.entry_id]: e.target.value })}
                            sx={{ width: 130 }}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Box>
          <Typography variant="caption" color="text.secondary">
            Receipt = customer pays (party ledger credit + account in). Payment = we pay a supplier (party debit + account out). One transaction.
          </Typography>
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">Payment types</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mt: 1 }}>
              {(paymentTypes.data ?? []).map((t) => (
                <Chip key={t.id} size="small" label={t.name} variant="outlined" />
              ))}
              <TextField size="small" label="Add type" value={newPayType}
                onChange={(e) => setNewPayType(e.target.value)} sx={{ width: 160 }} />
              <Button size="small" onClick={() => newPayType && addPayType.mutate()}
                disabled={addPayType.isPending || !newPayType}>Add</Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Expenses
          </Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (ex.account && ex.amount) addExpense.mutate(); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
              <TextField label="Category" select value={ex.category} onChange={(e) => setEx({ ...ex, category: e.target.value })} sx={{ minWidth: 160 }}>
                {(categories.data ?? []).map((c) => (<MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>))}
              </TextField>
              <TextField label="Paid from" select value={ex.account} onChange={(e) => setEx({ ...ex, account: e.target.value })} sx={{ minWidth: 160 }}>
                {(accounts.data ?? []).map((a) => (<MenuItem key={a.id} value={String(a.id)}>{a.name}</MenuItem>))}
              </TextField>
              <TextField label="Amount" value={ex.amount} onChange={(e) => setEx({ ...ex, amount: e.target.value })} sx={{ width: 120 }} />
              <TextField label="Note" value={ex.note} onChange={(e) => setEx({ ...ex, note: e.target.value })} />
              <Button type="submit" variant="contained" color="secondary" disabled={addExpense.isPending}>Add expense</Button>
            </Stack>
          </Box>
          <Stack spacing={0.5}>
            {(expenses.data ?? []).slice(0, 8).map((e: Expense) => (
              <Typography key={e.id} variant="body2">
                <code>{e.doc_no}</code> · {e.category ?? "—"} · ₹{e.amount} · from {accName(e.account_id)}
                {e.note ? ` · ${e.note}` : ""}
              </Typography>
            ))}
            {(expenses.data ?? []).length === 0 && (
              <Typography color="text.secondary" variant="body2">No expenses yet.</Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Vouchers
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Party</TableCell>
                <TableCell>Account</TableCell>
                <TableCell align="right">Amount</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(vouchers.data ?? []).map((x: Voucher) => (
                <TableRow key={x.id}>
                  <TableCell><code>{x.doc_no}</code></TableCell>
                  <TableCell>{x.voucher_type}</TableCell>
                  <TableCell>{partyName(x.party_id)}</TableCell>
                  <TableCell>{accName(x.account_id)}</TableCell>
                  <TableCell align="right">₹{x.amount}</TableCell>
                </TableRow>
              ))}
              {(vouchers.data ?? []).length === 0 && (
                <TableRow><TableCell colSpan={5}><Typography color="text.secondary">No vouchers yet.</Typography></TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  );
}
