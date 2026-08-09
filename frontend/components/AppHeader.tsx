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
    <header className="mx-auto flex max-w-3xl items-center justify-between border-b border-[var(--border)] pb-4">
      <div className="flex items-center gap-8">
        <Link
          href="/chat"
          className="font-mono text-sm font-semibold tracking-tight text-[var(--foreground)]"
        >
          sourcely
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          {LINKS.map((l) => {
            const isActive = l.href === `/${active}`;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={isActive ? "page" : undefined}
                className={
                  isActive
                    ? "relative font-semibold text-[var(--foreground)] after:absolute after:-bottom-[1.15rem] after:left-0 after:right-0 after:h-[2px] after:bg-[var(--foreground)] after:content-['']"
                    : "font-medium text-[var(--muted)] transition-colors hover:text-[var(--foreground)] focus-visible:text-[var(--foreground)]"
                }
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {email && (
          <span className="hidden text-[var(--muted)] sm:inline">{email}</span>
        )}
        <LogoutButton />
      </div>
    </header>
  );
}
