import axios from "axios";

// Default to a relative base so requests are same-origin and go through the
// Vite /api proxy (works locally and behind a single ngrok URL). Override with
// VITE_API_URL only if you want to point at an absolute backend.
const baseURL = import.meta.env.VITE_API_URL ?? "";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Skip ngrok's free-tier browser-warning interstitial on API (XHR) requests.
  config.headers["ngrok-skip-browser-warning"] = "true";
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      if (!location.pathname.startsWith("/login")) location.href = "/login";
    }
    return Promise.reject(err);
  },
);
