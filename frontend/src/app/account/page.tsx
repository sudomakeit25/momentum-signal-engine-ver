"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { User, Mail, Calendar, Lock, Pencil, Check, X } from "lucide-react";
import { useAuth, getAuthToken } from "@/hooks/use-auth";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface UserProfile {
  user_id: string;
  email: string;
  name: string;
  created_at: string;
}

function authedFetch<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const token = getAuthToken();
  const url = new URL(path, process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
  if (params) {
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null) url.searchParams.set(key, String(val));
    });
  }
  return fetch(url.toString(), {
    method: path.includes("change-password") || path.includes("update-name") ? "POST" : "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }).then((r) => {
    if (!r.ok) throw new Error(`API error: ${r.status}`);
    return r.json();
  });
}

export default function AccountPage() {
  const { user, isAuthenticated, loading, logout } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);

  // Name editing
  const [editingName, setEditingName] = useState(false);
  const [newName, setNewName] = useState("");
  const [nameMsg, setNameMsg] = useState("");

  // Password change
  const [showPassword, setShowPassword] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState(false);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push("/login");
    }
  }, [loading, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) {
      authedFetch<UserProfile>("/auth/me").then(setProfile).catch(() => {});
    }
  }, [isAuthenticated]);

  async function handleNameSave() {
    if (!newName.trim()) return;
    try {
      const res = await authedFetch<{ status: string; name?: string }>(
        "/auth/update-name",
        { name: newName.trim() }
      );
      if (res.status === "ok") {
        setProfile((p) => (p ? { ...p, name: res.name || newName.trim() } : p));
        setEditingName(false);
        setNameMsg("Name updated");
        // Update localStorage
        const saved = localStorage.getItem("mse-auth-user");
        if (saved) {
          const u = JSON.parse(saved);
          u.name = res.name || newName.trim();
          localStorage.setItem("mse-auth-user", JSON.stringify(u));
        }
        setTimeout(() => setNameMsg(""), 3000);
      }
    } catch {
      setNameMsg("Failed to update name");
    }
  }

  async function handlePasswordChange() {
    setPwMsg("");
    setPwError(false);

    if (newPw !== confirmPw) {
      setPwMsg("Passwords do not match");
      setPwError(true);
      return;
    }
    if (newPw.length < 6) {
      setPwMsg("Password must be at least 6 characters");
      setPwError(true);
      return;
    }

    try {
      const res = await authedFetch<{ status: string; message?: string }>(
        "/auth/change-password",
        { current_password: currentPw, new_password: newPw }
      );
      if (res.status === "ok") {
        setPwMsg("Password updated successfully");
        setPwError(false);
        setCurrentPw("");
        setNewPw("");
        setConfirmPw("");
        setShowPassword(false);
      } else {
        setPwMsg(res.message || "Failed to update password");
        setPwError(true);
      }
    } catch {
      setPwMsg("Failed to update password");
      setPwError(true);
    }
  }

  if (loading || !profile) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-zinc-500">
        Loading...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="flex items-center gap-3">
        <User className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Account</h1>
      </div>

      {/* Profile Card */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
        {/* Name */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <User className="h-4 w-4 text-zinc-500" />
            {editingName ? (
              <div className="flex items-center gap-2">
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleNameSave()}
                  className="h-7 w-40 bg-zinc-900 text-sm"
                  autoFocus
                />
                <button onClick={handleNameSave} className="text-emerald-400 hover:text-emerald-300">
                  <Check className="h-4 w-4" />
                </button>
                <button onClick={() => setEditingName(false)} className="text-zinc-500 hover:text-zinc-300">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-zinc-200">
                  {profile.name || "No name set"}
                </span>
                <button
                  onClick={() => {
                    setNewName(profile.name || "");
                    setEditingName(true);
                  }}
                  className="text-zinc-600 hover:text-zinc-400"
                >
                  <Pencil className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>
          {nameMsg && (
            <span className="text-xs text-emerald-400">{nameMsg}</span>
          )}
        </div>

        {/* Email */}
        <div className="flex items-center gap-3">
          <Mail className="h-4 w-4 text-zinc-500" />
          <span className="text-sm text-zinc-400">{profile.email}</span>
        </div>

        {/* Member Since */}
        <div className="flex items-center gap-3">
          <Calendar className="h-4 w-4 text-zinc-500" />
          <span className="text-sm text-zinc-400">
            Member since{" "}
            {profile.created_at
              ? new Date(profile.created_at).toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })
              : "Unknown"}
          </span>
        </div>

        {/* User ID */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-600">ID: {profile.user_id}</span>
        </div>
      </div>

      {/* Change Password */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Lock className="h-4 w-4 text-zinc-500" />
            <span className="text-sm font-medium text-zinc-200">Password</span>
          </div>
          {!showPassword && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPassword(true)}
              className="text-xs"
            >
              Change
            </Button>
          )}
        </div>

        {showPassword && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Current Password</Label>
              <Input
                type="password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                className="bg-zinc-900"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">New Password</Label>
              <Input
                type="password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                className="bg-zinc-900"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-400">Confirm New Password</Label>
              <Input
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handlePasswordChange()}
                className="bg-zinc-900"
              />
            </div>
            {pwMsg && (
              <p className={`text-xs ${pwError ? "text-red-400" : "text-emerald-400"}`}>
                {pwMsg}
              </p>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={handlePasswordChange}>
                Update Password
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setShowPassword(false);
                  setPwMsg("");
                  setCurrentPw("");
                  setNewPw("");
                  setConfirmPw("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Sign Out */}
      <Button
        variant="outline"
        className="w-full text-red-400 hover:text-red-300"
        onClick={() => {
          logout();
          router.push("/scanner");
        }}
      >
        Sign Out
      </Button>
    </div>
  );
}
