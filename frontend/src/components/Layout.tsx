import AccountBalanceWalletIcon from "@mui/icons-material/AccountBalanceWallet";
import AssessmentIcon from "@mui/icons-material/Assessment";
import GroupsIcon from "@mui/icons-material/Groups";
import Inventory2Icon from "@mui/icons-material/Inventory2";
import ManageAccountsIcon from "@mui/icons-material/ManageAccounts";
import MenuIcon from "@mui/icons-material/Menu";
import PointOfSaleIcon from "@mui/icons-material/PointOfSale";
import SettingsIcon from "@mui/icons-material/Settings";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import SpaceDashboardIcon from "@mui/icons-material/SpaceDashboard";
import StraightenIcon from "@mui/icons-material/Straighten";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import WarehouseIcon from "@mui/icons-material/Warehouse";
import {
  AppBar,
  Box,
  Button,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import type { ReactNode } from "react";
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../store/auth";
import { ErrorBoundary } from "./ErrorBoundary";

const DRAWER_WIDTH = 216;
const COLLAPSED_WIDTH = 60;

const NAV: { to: string; label: string; end: boolean; icon: ReactNode }[] = [
  { to: "/", label: "Dashboard", end: true, icon: <SpaceDashboardIcon /> },
  { to: "/parties", label: "Parties", end: false, icon: <GroupsIcon /> },
  { to: "/products", label: "Products", end: false, icon: <Inventory2Icon /> },
  { to: "/stock", label: "Stock", end: false, icon: <WarehouseIcon /> },
  { to: "/purchase", label: "Purchase", end: false, icon: <ShoppingCartIcon /> },
  { to: "/sales", label: "Sales", end: false, icon: <PointOfSaleIcon /> },
  { to: "/accounts", label: "Accounts", end: false, icon: <AccountBalanceWalletIcon /> },
  { to: "/reports", label: "Reports", end: false, icon: <AssessmentIcon /> },
  { to: "/transfers", label: "Transfers", end: false, icon: <SwapHorizIcon /> },
  { to: "/units", label: "Units", end: false, icon: <StraightenIcon /> },
  { to: "/users", label: "Users", end: false, icon: <ManageAccountsIcon /> },
  { to: "/settings", label: "Settings", end: false, icon: <SettingsIcon /> },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const navList = (showLabels: boolean) => (
    <List sx={{ px: 1 }}>
      {NAV.map((n) => (
        <ListItemButton
          key={n.to}
          component={NavLink}
          to={n.to}
          end={n.end}
          onClick={() => setMobileOpen(false)}
          title={n.label}
          sx={{
            borderRadius: 1.5,
            mb: 0.25,
            minHeight: 44,
            px: 1.25,
            justifyContent: showLabels ? "initial" : "center",
            color: "text.secondary",
            "&.active": {
              bgcolor: "action.selected",
              borderRight: "3px solid",
              borderColor: "secondary.main",
              color: "primary.main",
              "& .MuiListItemText-primary": { fontWeight: 700 },
              "& .MuiListItemIcon-root": { color: "primary.main" },
            },
          }}
        >
          <ListItemIcon sx={{ minWidth: 0, mr: showLabels ? 2 : "auto", justifyContent: "center", color: "inherit" }}>
            {n.icon}
          </ListItemIcon>
          <ListItemText
            primary={n.label}
            sx={{ opacity: showLabels ? 1 : 0, whiteSpace: "nowrap" }}
            primaryTypographyProps={{ fontSize: 14.5 }}
          />
        </ListItemButton>
      ))}
    </List>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="fixed" color="primary" elevation={0} sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            aria-label="menu"
            onClick={() => setMobileOpen((o) => !o)}
            sx={{ mr: 1, display: { md: "none" } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ fontWeight: 700, flexGrow: 1 }}>
            CHOLAVIN&#8209;ERP
          </Typography>
          <Typography variant="body2" sx={{ mr: 2, opacity: 0.85, display: { xs: "none", sm: "block" } }}>
            {user?.username}
          </Typography>
          <Button
            color="inherit"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Logout
          </Button>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: COLLAPSED_WIDTH }, flexShrink: { md: 0 } }}>
        {/* Mobile: hamburger drawer, always shows labels */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: "block", md: "none" },
            "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
          }}
        >
          <Toolbar />
          <Divider />
          {navList(true)}
        </Drawer>

        {/* Desktop: mini variant — icons only, expands on hover */}
        <Drawer
          variant="permanent"
          open
          onMouseEnter={() => setExpanded(true)}
          onMouseLeave={() => setExpanded(false)}
          sx={{
            display: { xs: "none", md: "block" },
            "& .MuiDrawer-paper": {
              width: expanded ? DRAWER_WIDTH : COLLAPSED_WIDTH,
              overflowX: "hidden",
              transition: "width 180ms ease",
              boxSizing: "border-box",
              boxShadow: expanded ? 4 : 0,
            },
          }}
        >
          <Toolbar />
          <Divider />
          {navList(expanded)}
        </Drawer>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, width: { md: `calc(100% - ${COLLAPSED_WIDTH}px)` }, minWidth: 0 }}>
        <Toolbar />
        <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: "100%", overflowX: "auto" }}>
          {/* keyed on the route so navigating away clears a failed page */}
          <ErrorBoundary key={pathname}>
            <Outlet />
          </ErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
