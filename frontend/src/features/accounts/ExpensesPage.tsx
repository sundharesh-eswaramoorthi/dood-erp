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

import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import { errorMessage } from "../../lib/api";
import {
  createExpenseCategory,
  listAccounts,
  listExpenseCategories,
  listExpenses,
  postExpense,
  type Expense,
} from "./api";

export function ExpensesPage() {
  const qc = useQueryClient();
  const scope = useBranchScope();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const categories = useQuery({ queryKey: ["expense-categories"], queryFn: listExpenseCategories });
  const expenses = useQuery({ queryKey: [...["expenses"], scope.branchId], queryFn: () => listExpenses(scope.branchId) });

  const [ex, setEx] = useState({ account: "", category: "", amount: "", note: "" });
  const [newCat, setNewCat] = useState("");
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (accounts.data?.length && !ex.account) setEx((s) => ({ ...s, account: String(accounts.data![0].id) }));
    if (categories.data?.length && !ex.category) setEx((s) => ({ ...s, category: String(categories.data![0].id) }));
  }, [accounts.data, categories.data, ex.account, ex.category]);

  const accName = (id: number) => accounts.data?.find((a) => a.id === id)?.name ?? id;

  const add = useMutation({
    mutationFn: () =>
      postExpense({
        account_id: Number(ex.account),
        amount: ex.amount,
        category_id: ex.category ? Number(ex.category) : null,
        note: ex.note,
      }),
    onSuccess: (r) => {
      setMsg({ text: `Expense ${r.doc_no}: account balance ₹${r.account_balance}.`, ok: true });
      setEx({ ...ex, amount: "", note: "" });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["expenses"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not record the expense"), ok: false }),
  });

  const addCat = useMutation({
    mutationFn: () => createExpenseCategory({ name: newCat }),
    onSuccess: () => {
      setNewCat("");
      qc.invalidateQueries({ queryKey: ["expense-categories"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not add the category"), ok: false }),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Expenses</Typography>
        <Typography color="text.secondary">
          Money out that is not owed to a party — rent, salary, transport. It leaves an
          account and reduces net profit.
        </Typography>
      </Box>
      <BranchFilter
        value={scope.branch}
        onChange={scope.setBranch}
        branches={scope.branches}
        helperText="expenses shown are this branch's"
      />
      {msg && <Alert severity={msg.ok ? "success" : "error"} onClose={() => setMsg(null)}>{msg.text}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Record an expense</Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (ex.account && ex.amount) add.mutate(); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField label="Category" select value={ex.category}
                onChange={(e) => setEx({ ...ex, category: e.target.value })} sx={{ minWidth: 170 }}>
                {(categories.data ?? []).map((c) => (<MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>))}
              </TextField>
              <TextField label="Paid from" select value={ex.account}
                onChange={(e) => setEx({ ...ex, account: e.target.value })} sx={{ minWidth: 170 }}>
                {(accounts.data ?? []).map((a) => (<MenuItem key={a.id} value={String(a.id)}>{a.name}</MenuItem>))}
              </TextField>
              <TextField label="Amount" value={ex.amount}
                onChange={(e) => setEx({ ...ex, amount: e.target.value })} sx={{ width: 130 }} />
              <TextField label="Note" value={ex.note}
                onChange={(e) => setEx({ ...ex, note: e.target.value })} sx={{ flex: 1, minWidth: 180 }} />
              <Button type="submit" variant="contained" color="secondary" disabled={add.isPending}>
                Add expense
              </Button>
            </Stack>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">New category:</Typography>
            <TextField size="small" value={newCat} onChange={(e) => setNewCat(e.target.value)} sx={{ width: 180 }} />
            <Button size="small" onClick={() => newCat && addCat.mutate()} disabled={addCat.isPending || !newCat}>
              Add
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Recent expenses</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Paid from</TableCell>
                <TableCell>Note</TableCell>
                <TableCell align="right">Amount</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(expenses.data ?? []).map((e: Expense) => (
                <TableRow key={e.id}>
                  <TableCell><code>{e.doc_no}</code></TableCell>
                  <TableCell>{e.category ?? "—"}</TableCell>
                  <TableCell>{accName(e.account_id)}</TableCell>
                  <TableCell>{e.note || "—"}</TableCell>
                  <TableCell align="right">₹{e.amount}</TableCell>
                </TableRow>
              ))}
              {(expenses.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography color="text.secondary">No expenses yet.</Typography>
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
