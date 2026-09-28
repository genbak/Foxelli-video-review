import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Foxelli · Video review",
  description: "Review video ads and leave timestamped feedback.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
