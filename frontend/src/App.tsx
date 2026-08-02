import { CssBaseline, ThemeProvider } from "@mui/material";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { queryClient } from "./app/queryClient";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { BankAccountsPage } from "./features/accounts/BankAccountsPage";
import { ExpensesPage } from "./features/accounts/ExpensesPage";
import { PaymentInPage, PaymentOutPage } from "./features/accounts/VoucherPage";
import { LoginPage } from "./features/auth/LoginPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { PartiesPage } from "./features/parties/PartiesPage";
import { PartyDetailPage } from "./features/parties/PartyDetailPage";
import { PrintPage } from "./features/printing/PrintPage";
import { ProductsPage } from "./features/products/ProductsPage";
import { PurchaseBillsPage } from "./features/purchase/PurchaseBillsPage";
import { PurchaseOrdersPage } from "./features/purchase/PurchaseOrdersPage";
import { PurchaseReturnsPage } from "./features/purchase/PurchaseReturnsPage";
import { ReportsPage } from "./features/reports/ReportsPage";
import { SaleOrdersPage } from "./features/sales/SaleOrdersPage";
import { SalesInvoicesPage } from "./features/sales/SalesInvoicesPage";
import { SalesReturnsPage } from "./features/sales/SalesReturnsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { StockPage } from "./features/stock/StockPage";
import { TransfersPage } from "./features/stock/TransfersPage";
import { UnitsPage } from "./features/units/UnitsPage";
import { UsersPage } from "./features/users/UsersPage";
import { theme } from "./theme";

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ErrorBoundary>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              {/* outside the Layout on purpose: the print view is the paper */}
              <Route
                path="/print/:docType/:docId"
                element={
                  <ProtectedRoute>
                    <PrintPage />
                  </ProtectedRoute>
                }
              />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<DashboardPage />} />
                <Route path="/parties" element={<PartiesPage />} />
                <Route path="/parties/:id" element={<PartyDetailPage />} />
                <Route path="/products" element={<ProductsPage />} />
                <Route path="/stock" element={<StockPage />} />
                <Route path="/transfers" element={<TransfersPage />} />

                {/* v2 §3/§4: order, invoice and return are separate documents
                    and now separate screens */}
                <Route path="/purchase/orders" element={<PurchaseOrdersPage />} />
                <Route path="/purchase/bills" element={<PurchaseBillsPage />} />
                <Route path="/purchase/returns" element={<PurchaseReturnsPage />} />
                <Route path="/sales/orders" element={<SaleOrdersPage />} />
                <Route path="/sales/invoices" element={<SalesInvoicesPage />} />
                <Route path="/sales/returns" element={<SalesReturnsPage />} />

                <Route path="/accounts/bank" element={<BankAccountsPage />} />
                <Route path="/accounts/payment-in" element={<PaymentInPage />} />
                <Route path="/accounts/payment-out" element={<PaymentOutPage />} />
                <Route path="/accounts/expenses" element={<ExpensesPage />} />

                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/units" element={<UnitsPage />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/settings" element={<SettingsPage />} />

                {/* the old single-page routes, so existing bookmarks still land */}
                <Route path="/purchase" element={<Navigate to="/purchase/bills" replace />} />
                <Route path="/sales" element={<Navigate to="/sales/invoices" replace />} />
                <Route path="/accounts" element={<Navigate to="/accounts/bank" replace />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
