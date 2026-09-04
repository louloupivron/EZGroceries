/**
 * Fetch Migros favorite products (Mes produits → favoris).
 * Requires MIGROS_EMAIL + MIGROS_PASSWORD (+ MIGROS_TOTP_SECRET if 2FA).
 */
import { api } from "migros-mcp/dist/auth/api.js";
import { credsFromEnv } from "migros-mcp/dist/auth-tools/_shared.js";
import { MigrosAPI } from "migros-api-wrapper";
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

function requireCreds() {
  const creds = credsFromEnv();
  if (!creds) {
    throw new Error(
      "Identifiants Migros requis : MIGROS_EMAIL et MIGROS_PASSWORD dans .env",
    );
  }
  return creds;
}

async function favorites() {
  requireCreds();
  const raw = await api("GET", "/shopping/public/v3/favorites/products", undefined, {
    creds: credsFromEnv(),
    language: "fr",
  });
  if (!raw?.length) {
    return { count: 0, favorites: [], products: [] };
  }

  const migros = new MigrosAPI();
  await migros.account.oauth2.loginGuestToken();
  const uids = raw.map((f) => String(f.id)).join(",");
  const details = await migros.products.productDisplay.getProductDetails({
    uids,
    storeType: "ONLINE",
  });
  const products = Array.isArray(details) ? details : Object.values(details);

  const enriched = raw.map((fav) => {
    const product = products.find((p) => p.uid === fav.id) ?? {};
    const offer = product.offer ?? {};
    const price = offer.price ?? {};
    return {
      uid: fav.id,
      migrosOnlineId: fav.migrosOnlineId,
      name: product.name ?? product.title ?? null,
      package: offer.quantity ?? null,
      price_chf: price.effectiveValue ?? price.advertisedValue ?? null,
      url: fav.migrosOnlineId
        ? `https://www.migros.ch/fr/product/${fav.migrosOnlineId}`
        : null,
      product,
    };
  });

  return { count: enriched.length, favorites: raw, products: enriched };
}

try {
  const result = await favorites();
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(JSON.stringify({ error: err.message }));
  process.exit(1);
}
