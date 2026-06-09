// src/api/axiosClient.ts
import axios from "axios";

export const axiosClient = axios.create({
  baseURL: "http://localhost:8001/api",
  timeout: 120000,
});

axiosClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      "Unexpected API error";

    return Promise.reject(new Error(message));
  }
);