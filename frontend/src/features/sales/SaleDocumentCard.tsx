import {
  Box,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import {
  SaleLinesEditor,
  emptyLine,
  isComplete,
  toPayload,
  toPreviewLines,
  type SaleLine,
} from "./SaleLines";

/** The sale order and the counter sale differ only in whether stock is reserved
 *  or moved and whether money changes hands now, so they share one editor. */
export function SaleDocumentCard({
  title,
  subtitle,
  actionLabel,
  customer,
  onCustomer,
  branch,
  onBranch,
  parties,
  branches,
  godowns,
  accounts,
  paymentTypes,
  showMoney,
  onSubmit,
  onError,
}: {
  title: string;
  subtitle: string;
  actionLabel: string;
  customer: string;
  onCustomer: (v: string) => void;
  branch: string;
  onBranch: (v: string) => void;
  parties: { id: number; name: string }[];
  branches: { id: number; name: string }[];
  godowns: { id: number; name: string; branch_id: number }[];
  accounts: { id: number; name: string }[];
  paymentTypes: { id: number; name: string }[];
  showMoney: boolean;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [lines, setLines] = useState<SaleLine[]>([emptyLine()]);
  const [money, setMoney] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [posting, setPosting] = useState(false);

  // a line's godown has to belong to the chosen branch — switching branch
  // repoints every line rather than leaving one pointing somewhere invalid
  useEffect(() => {
    const valid = new Set(godowns.map((g) => String(g.id)));
    const fallback = godowns[0] ? String(godowns[0].id) : "";
    setLines((ls) =>
      ls.map((l) => (l.godown_id && valid.has(l.godown_id) ? l : { ...l, godown_id: fallback })),
    );
  }, [godowns]);

  const previewLines = toPreviewLines(lines);
  const preview = useQuery({
    queryKey: ["money-preview", previewLines, money],
    queryFn: () => previewMoney(previewLines, money),
    enabled: previewLines.length > 0,
  });

  const ready = !!customer && !!branch && lines.some(isComplete);

  const submit = async () => {
    if (!ready) return;
    setPosting(true);
    try {
      await onSubmit({
        customer_id: Number(customer),
        branch_id: Number(branch),
        ...(showMoney ? moneyPayload(money) : {}),
        lines: toPayload(lines),
      });
      setLines([emptyLine(godowns[0] ? String(godowns[0].id) : "")]);
      setMoney({ ...EMPTY_MONEY });
    } catch (e) {
      onError(e);
    } finally {
      setPosting(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="caption" color="text.secondary">{subtitle}</Typography>

        <Box component="form" onSubmit={(e) => { e.preventDefault(); submit(); }} sx={{ mt: 2 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
              <TextField
                label="Customer" select size="small" value={customer}
                onChange={(e) => onCustomer(e.target.value)} sx={{ minWidth: 220 }}
              >
                {parties.map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
              </TextField>
              <TextField
                label="Branch" select size="small" value={branch}
                onChange={(e) => onBranch(e.target.value)} sx={{ minWidth: 180 }}
                helperText="the godowns below are this branch's"
              >
                {branches.map((b) => (<MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>))}
              </TextField>
            </Stack>

            <SaleLinesEditor
              lines={lines}
              onChange={setLines}
              godowns={godowns}
              onPriceModeHint={(inclusive) =>
                inclusive && setMoney((m) => ({ ...m, price_mode: "inclusive" }))
              }
            />

            <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
              {showMoney && (
                <Box sx={{ flex: 1 }}>
                  <MoneyFields value={money} onChange={setMoney} accounts={accounts}
                    paymentTypes={paymentTypes} compact />
                </Box>
              )}
              <Box sx={{ p: 2, bgcolor: "#FCFAF6", borderRadius: 1, ml: showMoney ? 0 : "auto" }}>
                <MoneyTotalsPanel totals={preview.data?.totals} />
                <Button
                  type="submit" variant="contained" fullWidth sx={{ mt: 2 }}
                  disabled={posting || !ready}
                >
                  {actionLabel}
                </Button>
              </Box>
            </Stack>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

/** v2 §4: the order supplies the lines, this collects the money block and
 *  shows server-computed totals before the invoice is posted. */
