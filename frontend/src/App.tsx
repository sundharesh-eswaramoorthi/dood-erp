import { CssBaseline, ThemeProvider } from "@mui/material";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { queryClient } from "./app/queryClient";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./features/auth/LoginPage";
import { PartiesPage } from "./features/parties/PartiesPage";
import { PartyDetailPage } from "./features/parties/PartyDetailPage";
import { ProductsPage } from "./features/products/ProductsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { UnitsPage } from "./features/units/UnitsPage";
import { theme } from "./theme";

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<PartiesPage />} />
              <Route path="/parties/:id" element={<PartyDetailPage />} />
              <Route path="/products" element={<ProductsPage />} />
              <Route path="/units" element={<UnitsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
