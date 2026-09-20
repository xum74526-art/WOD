import { defineConfig } from "@playwright/test";
import mockConfig from "./playwright.account-deletion.config";

// Reuse the isolated local server; every browser API call is intercepted.
export default defineConfig({ ...mockConfig, testMatch: "contact-phone.spec.ts" });
