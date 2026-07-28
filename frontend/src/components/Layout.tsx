import { AppBar, Box, Button, Container, Stack, Toolbar, Typography } from "@mui/material";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../store/auth";

const NAV = [
  { to: "/", label: "Parties", end: true },
  { to: "/products", label: "Products", end: false },
  { to: "/stock", label: "Stock", end: false },
  { to: "/purchase", label: "Purchase", end: false },
  { to: "/sales", label: "Sales", end: false },
  { to: "/accounts", label: "Accounts", end: false },
  { to: "/transfers", label: "Transfers", end: false },
  { to: "/units", label: "Units", end: false },
  { to: "/settings", label: "Settings", end: false },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ fontWeight: 700, mr: 4 }}>
            CHOLAVIN&#8209;ERP
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexGrow: 1 }}>
            {NAV.map((n) => (
              <Button
                key={n.to}
                color="inherit"
                component={NavLink}
                to={n.to}
                end={n.end}
                sx={{
                  "&.active": { bgcolor: "rgba(255,255,255,0.16)" },
                  textTransform: "none",
                  fontWeight: 600,
                }}
              >
                {n.label}
              </Button>
            ))}
          </Stack>
          <Typography variant="body2" sx={{ mr: 2, opacity: 0.85 }}>
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
      <Container sx={{ py: 4 }}>
        <Outlet />
      </Container>
    </Box>
  );
}
