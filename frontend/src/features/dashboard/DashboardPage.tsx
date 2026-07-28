import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";

import { getDashboard } from "./api";

function Stat({
  label,
  value,
  money = false,
  color = "text.primary",
}: {
  label: string;
  value: string | number;
  money?: boolean;
  color?: string;
}) {
  return (
    <Card elevation={1}>
      <CardContent sx={{ py: 2 }}>
        <Typography
          variant="overline"
          sx={{ color: "text.secondary", letterSpacing: ".08em", lineHeight: 1.4, display: "block" }}
        >
          {label}
        </Typography>
        <Typography variant="h5" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums", color, mt: 0.5 }}>
          {money ? "₹" : ""}
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

const QUICK = [
  { to: "/sales", label: "New sale" },
  { to: "/purchase", label: "New purchase" },
  { to: "/accounts", label: "Receipt / payment" },
  { to: "/stock", label: "Adjust stock" },
  { to: "/parties", label: "Add party" },
];

export function DashboardPage() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, refetchInterval: 30000 });
  const d = q.data;

  return (
    <Stack spacing={3}>
      <Stack direction="row" alignItems="baseline" spacing={2}>
        <Typography variant="h4" fontWeight={800}>
          Dashboard
        </Typography>
        {d?.cached && <Chip size="small" label="cached" variant="outlined" />}
      </Stack>

      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 2 }}>
        <Stat label="Today's Sales" value={d?.today_sales ?? "—"} money color="primary.main" />
        <Stat label="Today's Collection" value={d?.today_collection ?? "—"} money color="success.main" />
        <Stat label="Today's Purchase" value={d?.today_purchase ?? "—"} money />
        <Stat label="Today's Expenses" value={d?.today_expenses ?? "—"} money color="error.main" />
        <Stat label="Today's Orders" value={d?.today_orders ?? "—"} />
        <Stat label="Pending Deliveries" value={d?.pending_deliveries ?? "—"} color="warning.main" />
        <Stat label="Current Stock Value" value={d?.current_stock_value ?? "—"} money />
        <Stat label="Petty Cash" value={d?.petty_cash ?? "—"} money />
        <Stat label="Outstanding Receivable" value={d?.outstanding_receivable ?? "—"} money color="success.main" />
        <Stat label="Outstanding Payable" value={d?.outstanding_payable ?? "—"} money color="error.main" />
      </Box>

      <Card elevation={1}>
        <CardContent>
          <Typography variant="overline" color="text.secondary">
            Quick actions
          </Typography>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {QUICK.map((a) => (
              <Button key={a.to} component={RouterLink} to={a.to} variant="outlined" size="small">
                {a.label}
              </Button>
            ))}
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" }, gap: 2 }}>
        <Card elevation={1}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Top selling products
            </Typography>
            <Divider sx={{ mb: 1 }} />
            {(d?.top_selling ?? []).map((t, i) => (
              <Stack key={i} direction="row" justifyContent="space-between">
                <Typography variant="body2">{t.name}</Typography>
                <Typography variant="body2" fontWeight={700}>{t.qty}</Typography>
              </Stack>
            ))}
            {(d?.top_selling ?? []).length === 0 && <Typography color="text.secondary" variant="body2">No sales yet.</Typography>}
          </CardContent>
        </Card>

        <Card elevation={1}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Low stock alert
            </Typography>
            <Divider sx={{ mb: 1 }} />
            {(d?.low_stock ?? []).map((l, i) => (
              <Stack key={i} direction="row" justifyContent="space-between">
                <Typography variant="body2">{l.name}</Typography>
                <Chip size="small" color="warning" label={`${l.on_hand}/${l.min_qty}`} />
              </Stack>
            ))}
            {(d?.low_stock ?? []).length === 0 && <Typography color="text.secondary" variant="body2">Nothing below reorder level.</Typography>}
          </CardContent>
        </Card>

        <Card elevation={1}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Recent activity
            </Typography>
            <Divider sx={{ mb: 1 }} />
            {(d?.recent_activities ?? []).map((a, i) => (
              <Typography key={i} variant="body2" sx={{ fontFamily: "monospace", fontSize: 12 }}>
                {new Date(a.at).toLocaleTimeString()} · {a.topic}
              </Typography>
            ))}
            {(d?.recent_activities ?? []).length === 0 && <Typography color="text.secondary" variant="body2">No activity yet.</Typography>}
          </CardContent>
        </Card>
      </Box>
    </Stack>
  );
}
