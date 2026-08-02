import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  ListSubheader,
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
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { listPaymentTypes } from "../accounts/api";
import { listParties } from "../parties/api";
import { listCategories, listProducts } from "../products/api";
import { listGodowns } from "../stock/api";
import { listBranches } from "../users/api";
import { listReports, runReport, toCsv, type ReportFilters } from "./api";

/** Which extra filters each report group can use — a party filter on a stock
 *  report would just be noise. */
const FILTERS_FOR: Record<string, string[]> = {
  Sales: ["branch", "party", "product", "category", "payment_type"],
  Purchase: ["branch", "party", "product", "category"],
  Stock: ["branch", "godown", "product", "category"],
  Party: ["branch", "party", "payment_type"],
  Expense: ["branch", "category"],
  Delivery: ["branch", "party"],
  Profit: ["branch", "party", "category"],
};

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => today().slice(0, 8) + "01";

function pretty(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isNumeric(v: unknown) {
  return v != null && v !== "" && !Number.isNaN(Number(v));
}

export function ReportsPage() {
  const [key, setKey] = useState("sales_summary");
  const [f, setF] = useState<ReportFilters>({ date_from: monthStart(), date_to: today() });

  const catalogue = useQuery({ queryKey: ["report-catalogue"], queryFn: listReports });
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const categories = useQuery({ queryKey: ["categories"], queryFn: listCategories });
  const branches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  const godowns = useQuery({ queryKey: ["godowns"], queryFn: () => listGodowns() });
  const payTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const report = useQuery({
    queryKey: ["report", key, f],
    queryFn: () => runReport(key, f),
  });

  const grouped = useMemo(() => {
    const out: Record<string, { key: string; title: string }[]> = {};
    for (const r of catalogue.data?.reports ?? []) {
      (out[r.group] ||= []).push({ key: r.key, title: r.title });
    }
    return out;
  }, [catalogue.data]);

  const currentGroup = catalogue.data?.reports.find((r) => r.key === key)?.group ?? "Sales";
  const allowed = FILTERS_FOR[currentGroup] ?? [];
  const set = (k: keyof ReportFilters, v: unknown) =>
    setF((s) => ({ ...s, [k]: v === "" ? undefined : v }));

  const cols = report.data?.rows.length ? Object.keys(report.data.rows[0]) : [];

  const download = () => {
    if (!report.data) return;
    const blob = new Blob([toCsv(report.data)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${key}_${f.date_from}_${f.date_to}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>
          Reports
        </Typography>
        <Typography color="text.secondary">
          {catalogue.data?.count ?? 0} reports across {Object.keys(grouped).length} groups, read
          straight from the ledgers. Cancelled documents are excluded everywhere.
        </Typography>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
            <TextField
              label="Report"
              select
              value={key}
              onChange={(e) => setKey(e.target.value)}
              sx={{ minWidth: 280 }}
            >
              {Object.entries(grouped).flatMap(([group, items]) => [
                <ListSubheader key={group}>{group}</ListSubheader>,
                ...items.map((i) => (
                  <MenuItem key={i.key} value={i.key} sx={{ pl: 3 }}>
                    {i.title}
                  </MenuItem>
                )),
              ])}
            </TextField>
            <TextField
              label="From"
              type="date"
              InputLabelProps={{ shrink: true }}
              value={f.date_from}
              onChange={(e) => set("date_from", e.target.value)}
              sx={{ width: 170 }}
            />
            <TextField
              label="To"
              type="date"
              InputLabelProps={{ shrink: true }}
              value={f.date_to}
              onChange={(e) => set("date_to", e.target.value)}
              sx={{ width: 170 }}
            />

            {allowed.includes("branch") && (
              <TextField label="Branch" select value={f.branch_id ?? ""} sx={{ minWidth: 150 }}
                onChange={(e) => set("branch_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All branches</MenuItem>
                {(branches.data ?? []).map((b) => (<MenuItem key={b.id} value={b.id}>{b.name}</MenuItem>))}
              </TextField>
            )}
            {allowed.includes("party") && (
              <TextField label="Party" select value={f.party_id ?? ""} sx={{ minWidth: 170 }}
                onChange={(e) => set("party_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All parties</MenuItem>
                {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>))}
              </TextField>
            )}
            {allowed.includes("product") && (
              <TextField label="Product" select value={f.product_id ?? ""} sx={{ minWidth: 160 }}
                onChange={(e) => set("product_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All products</MenuItem>
                {(products.data ?? []).map((p) => (<MenuItem key={p.id} value={p.id}>{p.code}</MenuItem>))}
              </TextField>
            )}
            {allowed.includes("category") && (
              <TextField label="Category" select value={f.category_id ?? ""} sx={{ minWidth: 150 }}
                onChange={(e) => set("category_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All categories</MenuItem>
                {(categories.data ?? []).map((c) => (<MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>))}
              </TextField>
            )}
            {allowed.includes("godown") && (
              <TextField label="Godown" select value={f.godown_id ?? ""} sx={{ minWidth: 150 }}
                onChange={(e) => set("godown_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All godowns</MenuItem>
                {(godowns.data ?? []).map((g) => (<MenuItem key={g.id} value={g.id}>{g.name}</MenuItem>))}
              </TextField>
            )}
            {allowed.includes("payment_type") && (
              <TextField label="Payment type" select value={f.payment_type_id ?? ""} sx={{ minWidth: 160 }}
                onChange={(e) => set("payment_type_id", e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">All types</MenuItem>
                {(payTypes.data ?? []).map((t) => (<MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>))}
              </TextField>
            )}
            <Button variant="outlined" onClick={download}
              disabled={!report.data?.rows.length} sx={{ height: 56 }}>
              Export CSV
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {report.data && (
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="baseline" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
              <Typography variant="h6">{report.data.title}</Typography>
              <Chip size="small" label={report.data.group} variant="outlined" />
              <Typography variant="caption" color="text.secondary">
                {report.data.date_from} to {report.data.date_to}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
              {Object.entries(report.data.summary).map(([k, v]) => (
                <Box key={k} sx={{ px: 2, py: 1, bgcolor: "#FCFAF6", borderRadius: 1, minWidth: 130 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {pretty(k)}
                  </Typography>
                  <Typography variant="h6" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    {v ?? "—"}
                  </Typography>
                </Box>
              ))}
            </Stack>
            <Divider sx={{ mb: 1 }} />
            {report.isLoading ? (
              <Typography color="text.secondary">Loading…</Typography>
            ) : cols.length === 0 ? (
              <Typography color="text.secondary">No rows for this period.</Typography>
            ) : (
              <Box sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {cols.map((c) => (
                        <TableCell key={c} align={isNumeric(report.data!.rows[0][c]) ? "right" : "left"}>
                          {pretty(c)}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {report.data.rows.map((r, i) => (
                      <TableRow key={i}>
                        {cols.map((c) => (
                          <TableCell key={c} align={isNumeric(r[c]) ? "right" : "left"}
                            sx={{ fontVariantNumeric: "tabular-nums" }}>
                            {r[c] ?? "—"}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
            <Typography variant="caption" color="text.secondary">
              {report.data.rows.length} row{report.data.rows.length === 1 ? "" : "s"}
            </Typography>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
