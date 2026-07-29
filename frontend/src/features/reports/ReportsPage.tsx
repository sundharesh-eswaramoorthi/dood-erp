import {
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
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { runReport } from "./api";

const REPORTS = ["profit", "sales", "purchase", "stock", "party", "expense", "delivery"];

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function firstOfMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
const pretty = (s: string) => s.replace(/_/g, " ");
const isMoneyKey = (k: string) =>
  /total|amount|value|balance|receivable|payable|revenue|cogs|profit|expenses|taxable|tax/.test(k);
const fmt = (k: string, v: string | number) => (isMoneyKey(k) && v !== null && v !== undefined ? `₹${v}` : String(v));

export function ReportsPage() {
  const [report, setReport] = useState("profit");
  const [from, setFrom] = useState(firstOfMonth());
  const [to, setTo] = useState(today());

  const q = useQuery({
    queryKey: ["report", report, from, to],
    queryFn: () => runReport(report, from, to),
  });

  const rows = q.data?.rows ?? [];
  const cols = rows.length ? Object.keys(rows[0]) : [];

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Reports
      </Typography>

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
            <TextField label="Report" select value={report} onChange={(e) => setReport(e.target.value)} sx={{ minWidth: 180 }}>
              {REPORTS.map((r) => (
                <MenuItem key={r} value={r} sx={{ textTransform: "capitalize" }}>{r}</MenuItem>
              ))}
            </TextField>
            <TextField label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="overline" color="text.secondary">
            Summary
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {Object.entries(q.data?.summary ?? {}).map(([k, v]) => (
              <Chip
                key={k}
                label={`${pretty(k)}: ${fmt(k, v)}`}
                color={k.includes("profit") || k === "receivable" ? "primary" : k === "payable" || k === "cogs" || k === "expenses" ? "default" : "default"}
                variant={k.includes("profit") ? "filled" : "outlined"}
              />
            ))}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {q.isLoading ? (
            <Typography color="text.secondary">Loading…</Typography>
          ) : rows.length === 0 ? (
            <Typography color="text.secondary">No data for this range.</Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  {cols.map((c) => (
                    <TableCell key={c} sx={{ textTransform: "capitalize" }} align={isMoneyKey(c) ? "right" : "left"}>
                      {pretty(c)}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i}>
                    {cols.map((c) => (
                      <TableCell key={c} align={isMoneyKey(c) ? "right" : "left"} sx={{ fontVariantNumeric: "tabular-nums" }}>
                        {fmt(c, r[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
