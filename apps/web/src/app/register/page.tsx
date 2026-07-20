import { Suspense } from "react";
import type { Metadata } from "next";
import { AuthScreen } from "@/components/auth/auth-screen";

export const metadata: Metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <Suspense>
      <AuthScreen mode="register" />
    </Suspense>
  );
}
