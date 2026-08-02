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
import { useState } from "react";

import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import { errorMessage } from "../../lib/api";
import {
  createAccount,
  createPaymentType,
  listAccounts,
  listPaymentTypes,
  type Account,
} from "./api";

/** The two masters behind every payment: WHERE money sits (cash/bank accounts)
 *  and HOW it is taken (payment types). They are deliberately separate — a card
 *  swipe and a bank transfer can land in the same account. */
export function BankAccountsPage() {
  const qc = useQueryClient();
  const scope = useBranchScope();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const [acc, setAcc] = useState({ name: "", account_type: "bank", opening: "0" });
  const [newPayType, setNewPayType] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const addAcc = useMutation({
    mutationFn: () =>
      createAccount({
        name: acc.name,
        account_type: acc.account_type,
        opening_balance: acc.opening || "0",
        branch_id: scope.branchId,
      }),
    onSuccess: () => {
      setAcc({ name: "", account_type: "bank", opening: "0" });
      setMsg(null);
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e) => setMsg(errorMessage(e, "Could not add the account")),
  });

  const addPayType = useMutation({
    mutationFn: () => createPaymentType({ name: newPayType }),
    onSuccess: () => {
      setNewPayType("");
      qc.invalidateQueries({ queryKey: ["payment-types"] });
    },
    onError: (e) => setMsg(errorMessage(e, "Could not add the payment type")),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>Bank &amp; cash</Typography>
      {msg && <Alert severity="error" onClose={() => setMsg(null)}>{msg}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Accounts</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Each account belongs to a branch and only that branch can pay in or out of
            it. A new branch starts with none, so create its cash account here first.
          </Typography>
          <Table size="small" sx={{ mb: 2 }}>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Branch</TableCell>
                <TableCell align="right">Balance</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(accounts.data ?? []).map((a: Account) => (
                <TableRow key={a.id}>
                  <TableCell>{a.name}</TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" label={a.account_type.replace("_", " ")} />
                  </TableCell>
                  <TableCell>{scope.branchName(a.branch_id)}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    ₹{a.current_balance}
                  </TableCell>
                </TableRow>
              ))}
              {(accounts.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography color="text.secondary">No accounts yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (acc.name) addAcc.mutate(); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField size="small" label="Name" value={acc.name}
                onChange={(e) => setAcc({ ...acc, name: e.target.value })} />
              <TextField size="small" label="Type" select value={acc.account_type}
                onChange={(e) => setAcc({ ...acc, account_type: e.target.value })} sx={{ width: 140 }}>
                <MenuItem value="bank">Bank</MenuItem>
                <MenuItem value="cash">Cash</MenuItem>
                <MenuItem value="petty_cash">Petty cash</MenuItem>
              </TextField>
              <TextField size="small" label="Opening" value={acc.opening}
                onChange={(e) => setAcc({ ...acc, opening: e.target.value })} sx={{ width: 120 }} />
              <BranchFilter
                value={scope.branch}
                onChange={scope.setBranch}
                branches={scope.branches}
                helperText="the account belongs to this branch"
              />
              <Button type="submit" variant="outlined" disabled={addAcc.isPending}>Add account</Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Payment types</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            How money is taken, as opposed to where it lands. This is what
            Payment&nbsp;Mode-wise Sales groups by.
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            {(paymentTypes.data ?? []).map((t) => (
              <Chip key={t.id} size="small" label={t.name} variant="outlined" />
            ))}
            <TextField size="small" label="Add type" value={newPayType}
              onChange={(e) => setNewPayType(e.target.value)} sx={{ width: 160 }} />
            <Button size="small" onClick={() => newPayType && addPayType.mutate()}
              disabled={addPayType.isPending || !newPayType}>Add</Button>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
