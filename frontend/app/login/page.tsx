import { Suspense } from "react";
import { LoginClient } from "../components/LoginClient";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="page-shell">Loading sign in...</main>}>
      <LoginClient />
    </Suspense>
  );
}
