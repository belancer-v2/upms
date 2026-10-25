import type { ReactNode } from "react";

/** Text where [SQUARE BRACKET] parts are placeholders the owner still has to fill. They are highlighted so they cannot be missed. */
export function Ph({ text }: { text: string }): ReactNode {
  return <>{text.split(/(\[[^\]]+\])/g).map((p, i) => (/^\[[^\]]+\]$/.test(p) ? <mark key={i} className="ph">{p}</mark> : p))}</>;
}
