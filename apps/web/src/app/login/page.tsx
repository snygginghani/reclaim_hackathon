import { Suspense } from "react";
import type { Metadata } from "next";
import { AuthScreen } from "@/components/auth/auth-screen";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <Suspense>
      <AuthScreen mode="login" />
    </Suspense>
  );
}
