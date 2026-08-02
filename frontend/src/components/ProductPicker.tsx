import { Autocomplete, Box, Chip, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { listProducts, type Product } from "../features/products/api";

/** Type-ahead product search, used by every document line.
 *
 * The pickers this replaces were plain dropdowns showing only the product code,
 * which is unusable past a few dozen products and tells the operator nothing
 * about what they are selling. This searches code, name and HSN server-side and
 * shows the name, the stock on hand and the master rate on each row.
 */
export function ProductPicker({
  value,
  onChange,
  label = "Product",
  autoFocus,
  size = "small",
  width,
}: {
  value: number | null;
  onChange: (product: Product | null) => void;
  label?: string;
  autoFocus?: boolean;
  size?: "small" | "medium";
  width?: number | string;
}) {
  const [input, setInput] = useState("");

  // The catalogue is small enough to hold client-side; the server still does
  // the matching so code/name/HSN all search alike.
  const products = useQuery({
    queryKey: ["products", "picker", input],
    queryFn: () => listProducts({ q: input || undefined, is_active: true, limit: 50 }),
    staleTime: 30_000,
  });

  const options = products.data ?? [];
  const selected = useMemo(
    () => options.find((p) => p.id === value) ?? null,
    [options, value],
  );

  return (
    <Autocomplete
      size={size}
      sx={{ width, minWidth: width ? undefined : 260 }}
      options={options}
      value={selected}
      loading={products.isLoading}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, p) => onChange(p)}
      getOptionLabel={(p) => (p ? `${p.name} · ${p.code}` : "")}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      // the server already matched; filtering again hides valid hits
      filterOptions={(x) => x}
      renderOption={(props, p) => {
        const { key, ...rest } = props as React.HTMLAttributes<HTMLLIElement> & { key: string };
        return (
          <Box component="li" key={key} {...rest}>
            <Stack sx={{ width: "100%" }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" sx={{ flex: 1 }}>{p.name}</Typography>
                {p.sale_price && (
                  <Typography variant="caption" color="text.secondary">
                    ₹{p.sale_price}
                  </Typography>
                )}
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="caption" color="text.secondary">{p.code}</Typography>
                {p.stock_qty != null && (
                  <Chip
                    size="small"
                    variant="outlined"
                    color={Number(p.stock_qty) > 0 ? "default" : "warning"}
                    label={`${Number(p.stock_qty)} in stock`}
                    sx={{ height: 18, fontSize: 11 }}
                  />
                )}
                {p.hsn_code && (
                  <Typography variant="caption" color="text.secondary">
                    HSN {p.hsn_code}
                  </Typography>
                )}
              </Stack>
            </Stack>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField {...params} label={label} autoFocus={autoFocus} placeholder="name, code or HSN" />
      )}
    />
  );
}
