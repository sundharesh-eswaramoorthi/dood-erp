import MenuIcon from "@mui/icons-material/Menu";
import {
  AppBar,
  Box,
  Button,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../store/auth";

const DRAWER_WIDTH = 216;

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/parties", label: "Parties", end: false },
  { to: "/products", label: "Products", end: false },
  { to: "/stock", label: "Stock", end: false },
  { to: "/purchase", label: "Purchase", end: false },
  { to: "/sales", label: "Sales", end: false },
  { to: "/accounts", label: "Accounts", end: false },
  { to: "/reports", label: "Reports", end: false },
  { to: "/transfers", label: "Transfers", end: false },
  { to: "/units", label: "Units", end: false },
  { to: "/users", label: "Users", end: false },
  { to: "/settings", label: "Settings", end: false },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const drawer = (
    <Box sx={{ overflow: "auto" }}>
      <Toolbar />
      <Divider />
      <List sx={{ px: 1 }}>
        {NAV.map((n) => (
          <ListItemButton
            key={n.to}
            component={NavLink}
            to={n.to}
            end={n.end}
            onClick={() => setMobileOpen(false)}
            sx={{
              borderRadius: 1.5,
              mb: 0.25,
              "&.active": {
                bgcolor: "action.selected",
                borderRight: "3px solid",
                borderColor: "secondary.main",
                "& .MuiListItemText-primary": { fontWeight: 700, color: "primary.main" },
              },
            }}
          >
            <ListItemText primary={n.label} primaryTypographyProps={{ fontSize: 14.5 }} />
          </ListItemButton>
        ))}
      </List>
    </Box>
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

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        {/* Mobile: temporary drawer opened by the hamburger */}
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
          {drawer}
        </Drawer>
        {/* Desktop: permanent sidebar */}
        <Drawer
          variant="permanent"
          open
          sx={{
            display: { xs: "none", md: "block" },
            "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
          }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{ flexGrow: 1, width: { md: `calc(100% - ${DRAWER_WIDTH}px)` }, minWidth: 0 }}
      >
        <Toolbar />
        <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: "100%", overflowX: "auto" }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
