import { createTheme } from "@mui/material/styles";

// Ledger navy + kraft ochre — the same identity as the plan documents.
export const theme = createTheme({
  palette: {
    primary: { main: "#1E3A5F" },
    secondary: { main: "#B96D28" },
    background: { default: "#F8F7F3", paper: "#FFFFFF" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily:
      'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
});
