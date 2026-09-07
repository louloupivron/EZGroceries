import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { api } from "migros-mcp/dist/auth/api.js";
import { credsFromEnv } from "migros-mcp/dist/auth-tools/_shared.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
for (const line of readFileSync(resolve(ROOT, ".env"), "utf8").split("\n")) {
  const t = line.trim();
  if (!t || t.startsWith("#") || !t.includes("=")) continue;
  const eq = t.indexOf("=");
  const k = t.slice(0, eq).trim();
  const v = t.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
  if (k && !process.env[k]) process.env[k] = v;
}

const listId = process.env.MIGROS_SHOPPING_LIST_ID;
const data = await api(
  "GET",
  `/shopping-list/public/v2/list/details?shoppingListId=${listId}`,
  undefined,
  { creds: credsFromEnv() },
);

console.log("shoppingListId:", data.shoppingListId);
console.log("name:", data.name);
console.log("slug:", data.slug ?? data.publicSlug ?? data.shareSlug ?? data.listSlug ?? "(absent)");
console.log("shareUrl:", data.shareUrl ?? data.publicUrl ?? "(absent)");
const items = (data.categories ?? []).flatMap((c) =>
  (c.items ?? []).map((i) => ({
    id: i.id,
    name: i.name ?? i.productName ?? i.title ?? null,
    quantity: i.quantity,
    category: c.name,
  })),
);
console.log("items:", items.length);
for (const it of items) {
  console.log(`  - ${it.name ?? "?"} (id ${it.id})`);
}
console.log("\nRaw keys on data:", Object.keys(data).join(", "));
