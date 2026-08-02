import { MenuItem, TextField } from "@mui/material";

/** The branch selector, identical on every screen.
 *
 * Hidden when the user works in a single branch: there is nothing to choose,
 * and an unchangeable dropdown reads as a control that is broken.
 */
export function BranchFilter({
  value,
  onChange,
  branches,
  label = "Branch",
  helperText,
  width = 180,
  size = "small",
}: {
  value: string;
  onChange: (v: string) => void;
  branches: { id: number; name: string }[];
  label?: string;
  helperText?: string;
  width?: number | string;
  size?: "small" | "medium";
}) {
  if (branches.length <= 1) return null;
  return (
    <TextField
      size={size}
      label={label}
      select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      helperText={helperText}
      sx={{ width }}
    >
      {branches.map((b) => (
        <MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>
      ))}
    </TextField>
  );
}
