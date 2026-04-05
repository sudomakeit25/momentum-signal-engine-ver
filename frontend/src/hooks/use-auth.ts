"use client";

import { useState, useEffect, useCallback } from "react";
import { apiPost, apiFetch } from "@/lib/api";

const TOKEN_KEY = "mse-auth-token";
const USER_KEY = "mse-auth-user";

interface User {
  user_id: string;
  email: string;
  name?: string;
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedToken = localStorage.getItem(TOKEN_KEY);
    const savedUser = localStorage.getItem(USER_KEY);
    if (savedToken && savedUser) {
      setToken(savedToken);
      try {
        setUser(JSON.parse(savedUser));
      } catch {
        // invalid saved user
      }
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiPost<{
      status: string;
      message?: string;
      user_id?: string;
      email?: string;
      name?: string;
      token?: string;
    }>("/auth/login", { email, password });

    if (res.status === "error") {
      throw new Error(res.message || "Login failed");
    }

    const userData = { user_id: res.user_id!, email: res.email!, name: res.name };
    localStorage.setItem(TOKEN_KEY, res.token!);
    localStorage.setItem(USER_KEY, JSON.stringify(userData));
    setToken(res.token!);
    setUser(userData);
    return userData;
  }, []);

  const register = useCallback(async (email: string, password: string, name?: string) => {
    const params: Record<string, string> = { email, password };
    if (name) params.name = name;

    const res = await apiPost<{
      status: string;
      message?: string;
      user_id?: string;
      email?: string;
      name?: string;
      token?: string;
    }>("/auth/register", params);

    if (res.status === "error") {
      throw new Error(res.message || "Registration failed");
    }

    const userData = { user_id: res.user_id!, email: res.email!, name: res.name };
    localStorage.setItem(TOKEN_KEY, res.token!);
    localStorage.setItem(USER_KEY, JSON.stringify(userData));
    setToken(res.token!);
    setUser(userData);
    return userData;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return { user, token, loading, login, register, logout, isAuthenticated: !!token };
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
