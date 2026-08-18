import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional Tailwind classes, letting a later class in the list
 * override an earlier conflicting one (e.g. a caller-supplied `className`
 * overriding a component's default padding). Standard shadcn/magicui
 * convention — added because several vendored magicui components import
 * from "@/lib/utils". */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
