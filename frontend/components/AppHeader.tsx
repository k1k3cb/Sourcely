import Link from "next/link";

import { LogoutButton } from "@/components/LogoutButton";

type NavLink = { href: string; label: string };

const LINKS: NavLink[] = [
  { href: "/chat", label: "Chat" },
  { href: "/documents", label: "Documents" },
];

export function AppHeader({
  email,
  active,
}: {
  email?: string | null;
  active: "chat" | "documents";
}) {
  return (
    <header className="mx-auto flex max-w-3xl items-center justify-between border-b border-zinc-200 pb-4 dark:border-zinc-800">
      <div className="flex items-center gap-6">
        <Link
          href="/chat"
          className="font-mono text-sm font-semibold tracking-tight"
        >
          sourcely
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {LINKS.map((l) => {
            const isActive = l.href === `/${active}`;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={isActive ? "page" : undefined}
                className={
                  isActive
                    ? "font-medium text-zinc-900 dark:text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                }
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {email && <span className="text-zinc-500">{email}</span>}
        <LogoutButton />
      </div>
    </header>
  );
}
