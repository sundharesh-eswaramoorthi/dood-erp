import { Alert, AlertTitle, Box, Button, Stack, Typography } from "@mui/material";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps one bad render from taking the whole app white.
 *
 * React unmounts the entire tree when a render throws, so before this a single
 * unrenderable value — an API validation payload passed into JSX, say — left a
 * blank page with no clue what happened. Now the failure stays on the page and
 * says so.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <Box sx={{ p: 3, maxWidth: 720, mx: "auto" }}>
        <Alert severity="error">
          <AlertTitle>Something broke on this screen</AlertTitle>
          <Typography variant="body2" sx={{ mb: 2 }}>
            The rest of the app is fine — this page failed to render.
          </Typography>
          <Typography variant="caption" component="pre" sx={{ whiteSpace: "pre-wrap", opacity: 0.8 }}>
            {error.message}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button size="small" variant="contained" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button size="small" onClick={() => (location.href = "/")}>
              Go to dashboard
            </Button>
          </Stack>
        </Alert>
      </Box>
    );
  }
}
