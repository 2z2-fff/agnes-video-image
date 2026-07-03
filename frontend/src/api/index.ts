import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

// Response interceptor: extract error detail from FastAPI error responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data?.detail) {
      return Promise.reject(new Error(error.response.data.detail));
    }
    return Promise.reject(error);
  }
);

export default api;
