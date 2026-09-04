/**
 * CLI bridge to migros-api-wrapper. Outputs JSON on stdout.
 */
import { MigrosAPI } from "migros-api-wrapper";

const api = new MigrosAPI();

async function ensureGuest() {
  await api.account.oauth2.loginGuestToken();
}

function parseIds(arg) {
  return arg.split(",").map((s) => Number(s.trim())).filter(Boolean);
}

async function promotions({ from = 0, until = 100, store = "ONLINE" }) {
  await ensureGuest();
  const data = await api.products.productDisplay.getProductPromotionSearch({
    language: "fr",
    from: Number(from),
    until: Number(until),
    storeType: store,
    filters: {},
  });
  return {
    startDate: data.startDate,
    endDate: data.endDate,
    numberOfItems: data.numberOfItems,
    items: data.items ?? [],
  };
}

async function details({ ids, store = "ONLINE" }) {
  await ensureGuest();
  const uidList = parseIds(ids);
  if (!uidList.length) throw new Error("No product ids provided");
  const data = await api.products.productDisplay.getProductDetails({
    uids: uidList.join(","),
    storeType: store,
  });
  return data;
}

async function search({ query, size = 10, lang = "fr" }) {
  await ensureGuest();
  const data = await api.products.productSearch.searchProduct(
    { query, language: lang, pageSize: Number(size) },
    {},
  );
  const ids = data.productIds ?? [];
  if (!ids.length) return { productIds: [], products: [] };
  const products = await api.products.productDisplay.getProductDetails({
    uids: ids.join(","),
    storeType: "ONLINE",
  });
  return { productIds: ids, products };
}

const commands = { promotions, details, search };

const [cmd, ...rest] = process.argv.slice(2);
if (!cmd || !commands[cmd]) {
  console.error(`Usage: node migros.mjs <${Object.keys(commands).join("|")}> [--key value ...]`);
  process.exit(1);
}

const args = {};
for (let i = 0; i < rest.length; i += 2) {
  const key = rest[i]?.replace(/^--/, "");
  const val = rest[i + 1];
  if (key && val) args[key] = val;
}

try {
  const result = await commands[cmd](args);
  console.log(JSON.stringify(result));
} catch (err) {
  console.error(JSON.stringify({ error: err.message, data: err.response?.data }));
  process.exit(1);
}
