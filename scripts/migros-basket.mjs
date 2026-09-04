/**
 * Authenticated Migros basket operations (via migros-mcp).
 * Requires MIGROS_EMAIL + MIGROS_PASSWORD (+ MIGROS_TOTP_SECRET if 2FA).
 *
 * Optional: MIGROS_SHOPPING_LIST_ID or MIGROS_SHOPPING_LIST_NAME (see `lists` command).
 * Shared URL slug (e.g. 4SOsOT53) is not the same as shoppingListId.
 */
import { addToBasket, getBasket, getCheckoutLink } from "migros-mcp/dist/auth-tools/cart.js";
import { api } from "migros-mcp/dist/auth/api.js";
import { credsFromEnv } from "migros-mcp/dist/auth-tools/_shared.js";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function loadDotenv() {
  const envPath = resolve(ROOT, ".env");
  if (!existsSync(envPath)) return;
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const eq = trimmed.indexOf("=");
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
    if (key && process.env[key] === undefined) process.env[key] = val;
  }
}

loadDotenv();

function shoppingListId() {
  const raw = process.env.MIGROS_SHOPPING_LIST_ID;
  return raw ? Number(raw) : undefined;
}

async function resolveShoppingListId() {
  const byId = shoppingListId();
  if (byId) return byId;

  const nameFilter = process.env.MIGROS_SHOPPING_LIST_NAME?.trim();
  if (nameFilter) {
    requireCreds();
    const lists = await api("GET", "/shopping-list/public/v1/lists/overview", undefined, {
      creds: credsFromEnv(),
    });
    const needle = nameFilter.toLowerCase();
    const match = lists.find((l) =>
      (l.shoppingListName || l.name || "").toLowerCase().includes(needle),
    );
    if (!match) {
      const names = lists.map((l) => l.shoppingListName || l.name || `id ${l.shoppingListId}`).join(", ");
      throw new Error(
        `Liste « ${nameFilter} » introuvable. Listes disponibles : ${names}`,
      );
    }
    return match.shoppingListId;
  }

  return undefined;
}

function requireCreds() {
  const creds = credsFromEnv();
  if (!creds) {
    throw new Error(
      "Identifiants Migros requis : MIGROS_EMAIL et MIGROS_PASSWORD dans .env (voir .env.example)",
    );
  }
  return creds;
}

async function lists() {
  requireCreds();
  const data = await api("GET", "/shopping-list/public/v1/lists/overview", undefined, {
    creds: credsFromEnv(),
  });
  return data;
}

async function basket() {
  requireCreds();
  const listId = await resolveShoppingListId();
  return JSON.parse(await getBasket({ shoppingListId: listId }));
}

async function add({ id, quantity = "1" }) {
  requireCreds();
  const listId = await resolveShoppingListId();
  const productId = Number(id);
  const qty = Number(quantity);
  const raw = await addToBasket({
    productId,
    quantity: qty,
    shoppingListId: listId,
  });
  return { productId, quantity: qty, shoppingListId: listId, basket: JSON.parse(raw) };
}

async function push({ items }) {
  requireCreds();
  const parsed = JSON.parse(items);
  const listId = await resolveShoppingListId();
  const results = [];
  for (const item of parsed) {
    const productId = Number(item.uid ?? item.productId ?? item.id);
    const quantity = Number(item.quantity ?? 1);
    if (!productId) continue;
    try {
      const raw = await addToBasket({ productId, quantity, shoppingListId: listId });
      results.push({
        productId,
        quantity,
        ingredient: item.ingredient_name ?? item.name,
        ok: true,
        itemCount: JSON.parse(raw).itemCount,
      });
    } catch (err) {
      results.push({
        productId,
        quantity,
        ingredient: item.ingredient_name ?? item.name,
        ok: false,
        error: err.message,
      });
    }
  }
  const checkout = JSON.parse(await getCheckoutLink());
  const basketData = JSON.parse(await getBasket({ shoppingListId: listId }));
  return { shoppingListId: listId, results, checkout, basket: basketData };
}

const commands = { lists, basket, add, push };

const [cmd, ...rest] = process.argv.slice(2);
if (!cmd || !commands[cmd]) {
  console.error(`Usage: node migros-basket.mjs <${Object.keys(commands).join("|")}> [--key value ...]`);
  process.exit(1);
}

const args = {};
for (let i = 0; i < rest.length; i += 2) {
  const key = rest[i]?.replace(/^--/, "");
  const val = rest[i + 1];
  if (key && val !== undefined) args[key] = val;
}

try {
  const result = await commands[cmd](args);
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(JSON.stringify({ error: err.message }));
  process.exit(1);
}
