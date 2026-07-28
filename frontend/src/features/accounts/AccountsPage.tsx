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
import { createAccount, listAccounts, listVouchers, postVoucher, type Account, type Voucher } from "./api";

export function AccountsPage() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const vouchers = useQuery({ queryKey: ["vouchers"], queryFn: listVouchers });

  const [acc, setAcc] = useState({ name: "", account_type: "bank", opening: "0" });
  const [v, setV] = useState({ party: "", account: "", type: "receipt", amount: "", note: "" });
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (parties.data?.length && !v.party) setV((s) => ({ ...s, party: String(parties.data![0].id) }));
    if (accounts.data?.length && !v.account) setV((s) => ({ ...s, account: String(accounts.data![0].id) }));
  }, [parties.data, accounts.data, v.party, v.account]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;
  const accName = (id: number) => accounts.data?.find((a) => a.id === id)?.name ?? id;

  const addAcc = useMutation({
    mutationFn: () => createAccount({ name: acc.name, account_type: acc.account_type, opening_balance: acc.opening || "0" }),
    onSuccess: () => {
      setAcc({ name: "", account_type: "bank", opening: "0" });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const pay = useMutation({
    mutationFn: () =>
      postVoucher({ party_id: Number(v.party), account_id: Number(v.account), voucher_type: v.type, amount: v.amount, note: v.note }),
    onSuccess: (r) => {
      setMsg(`${r.doc_no}: account balance ₹${r.account_balance}, party net ₹${r.party_net}.`);
      setV({ ...v, amount: "", note: "" });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["vouchers"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Voucher failed");
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
              <TextField label="Note" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} />
              <Button type="submit" variant="contained" disabled={pay.isPending}>Post</Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Receipt = customer pays (party ledger credit + account in). Payment = we pay a supplier (party debit + account out). One transaction.
          </Typography>
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
