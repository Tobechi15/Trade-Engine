"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";

import { useAuthStore } from "@/lib/auth-store";

function useHasHydrated() {
  // useSyncExternalStore is the SSR-safe way to read zustand's persist
  // hydration state: the server snapshot is always `false` (no
  // localStorage there), and the client re-subscribes to the store's own
  // hydration event once mounted - no manual effect/setState dance needed.
  return useSyncExternalStore(
    (callback) => useAuthStore.persist.onFinishHydration(callback),
    () => useAuthStore.persist.hasHydrated(),
    () => false,
  );
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const router = useRouter();
  const hydrated = useHasHydrated();

  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  if (!hydrated || !token) {
    return null;
  }

  return <>{children}</>;
}
