import axios, { type InternalAxiosRequestConfig } from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true, // send HttpOnly refresh_token cookie automatically
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    // Never retry auth endpoints — prevents an infinite refresh loop when
    // authApi.refresh() itself 401s (no valid session cookie on first load).
    const isAuthEndpoint = original?.url?.startsWith("/auth/");
    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true;
      try {
        // No body needed — refresh_token cookie is sent automatically
        const { data } = await axios.post("/api/auth/refresh", undefined, { withCredentials: true });
        localStorage.setItem("access_token", data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch {
        localStorage.removeItem("access_token");
        // Soft signal to AuthContext — avoids a hard page reload that would
        // restart the cycle. AuthContext clears state; React Router navigates.
        window.dispatchEvent(new Event("auth:session-expired"));
      }
    }
    return Promise.reject(error);
  }
);

export default api;