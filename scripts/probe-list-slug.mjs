import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { api } from "migros-mcp/dist/auth/api.js";
import { credsFromEnv } from "migros-mcp/dist/auth-tools/_shared.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const envPath = resolve(ROOT, ".env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const eq = trimmed.indexOf("=");
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
    if (key && process.env[key] === undefined) process.env[key] = val;
  }
}

const slug = process.env.MIGROS_LIST_SLUG || "iQapzRdY";
const listId = process.env.MIGROS_SHOPPING_LIST_ID;
const creds = credsFromEnv();

const candidates = [
  `/shopping-list/public/v1/lists/${listId}`,
  `/shopping-list/public/v1/lists/${listId}/items`,
  `/shopping-list/public/v1/shared-lists/${slug}`,
  `/shopping-list/public/v1/lists/slug/${slug}`,
  `/shopping/public/v3/shopping-lists/slug/${slug}`,
  `/shopping/public/v3/lists/${slug}`,
];

for (const path of candidates) {
  try {
    const data = await api("GET", path, undefined, { creds });
    console.log("OK", path, JSON.stringify(data).slice(0, 800));
  } catch (err) {
    console.log("ERR", path, err.message?.slice(0, 150));
  }
}
