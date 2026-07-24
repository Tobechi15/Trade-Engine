"use client";

import { useEffect, useState } from "react";

const ET_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function LiveClock() {
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="hidden items-center gap-1.5 text-sm text-muted-foreground sm:flex">
      <span className="font-mono">{ET_FORMATTER.format(now)}</span>
      <span className="text-xs">ET</span>
    </div>
  );
}
