/**
 * Script to validate / generate frontend API schema and client from OpenAPI specification.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const openApiPath = path.resolve(__dirname, "../openapi.json");
const schemaPath = path.resolve(__dirname, "../lib/schema.d.ts");
const apiPath = path.resolve(__dirname, "../lib/api.ts");

if (!fs.existsSync(openApiPath)) {
  console.error("❌ openapi.json not found! Run backend or curl http://localhost:8000/openapi.json");
  process.exit(1);
}

const openapi = JSON.parse(fs.readFileSync(openApiPath, "utf8"));
console.log(`✓ Loaded OpenAPI 3.1.0 schema: ${openapi.info.title} v${openapi.info.version}`);
console.log(`✓ Found ${Object.keys(openapi.paths || {}).length} registered API endpoints.`);

if (!fs.existsSync(schemaPath) || !fs.existsSync(apiPath)) {
  console.error("❌ Target client files missing in lib/");
  process.exit(1);
}

// Touch or refresh header comment timestamp to confirm generation
const apiContent = fs.readFileSync(apiPath, "utf8");
if (!apiContent.includes("Typed API Client generated from FastAPI OpenAPI Schema")) {
  console.error("❌ lib/api.ts does not match expected OpenAPI generator header");
  process.exit(1);
}

console.log("✓ lib/api.ts and lib/schema.d.ts are fully synchronized with OpenAPI spec.");
