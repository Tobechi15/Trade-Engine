import {
  LayoutDashboard,
  Radar,
  Bot,
  ListOrdered,
  Wallet,
  LineChart,
  ScrollText,
  ShieldAlert,
  Settings,
  Bell,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/scanner", label: "Scanner", icon: Radar },
  { href: "/strategies", label: "Strategies", icon: Bot },
  { href: "/orders", label: "Orders", icon: ListOrdered },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/logs", label: "Logs", icon: ScrollText },
  { href: "/risk", label: "Risk", icon: ShieldAlert },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
];
