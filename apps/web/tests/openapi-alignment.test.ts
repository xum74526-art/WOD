import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

type SchemaReference = { $ref?: string; anyOf?: SchemaReference[] };
type Operation = { parameters?: Array<{ name: string }>; requestBody?: { required?: boolean; content?: { "application/json"?: { schema?: SchemaReference } } }; responses?: Record<string, unknown> };
type PropertySchema = { type?: string; minLength?: number; maxLength?: number; pattern?: string; anyOf?: PropertySchema[] };
type OpenApi = { paths: Record<string, Record<string, Operation>>; components: { schemas: Record<string, { properties?: Record<string, PropertySchema>; required?: string[] }> } };
const contractPath = fileURLToPath(new URL("../../../packages/api-contracts/openapi.json", import.meta.url));
const contract = JSON.parse(readFileSync(contractPath, "utf8")) as OpenApi;

function operation(path: string, method: "get" | "post" | "put" | "delete") {
  const value = contract.paths[path]?.[method];
  assert.ok(value, `${method.toUpperCase()} ${path} must exist in the exported OpenAPI contract`);
  return value;
}

function bodySchema(path: string, method: "post" | "put") {
  const requestSchema = operation(path, method).requestBody?.content?.["application/json"]?.schema;
  const ref = requestSchema?.$ref ?? requestSchema?.anyOf?.find((item) => item.$ref)?.$ref;
  assert.ok(ref, `${method.toUpperCase()} ${path} must declare a JSON request schema`);
  const schema = contract.components.schemas[ref.split("/").at(-1)!];
  assert.ok(schema, `${ref} must resolve`);
  return schema;
}

test("authentication contract records Web origin and supports explicit Kai binding", () => {
  assert.ok(bodySchema("/api/auth/login", "post").properties?.client_id);
  const registration = bodySchema("/api/auth/register", "post");
  assert.ok(registration.properties?.client_id);
  const inviteCode = registration.properties?.invite_code?.anyOf?.find((item) => item.type === "string");
  assert.deepEqual(
    {
      usernameMin: registration.properties?.username?.minLength,
      usernameMax: registration.properties?.username?.maxLength,
      passwordMin: registration.properties?.password?.minLength,
      passwordMax: registration.properties?.password?.maxLength,
      inviteCodeMax: inviteCode?.maxLength,
      captchaKey: registration.properties?.captcha_key?.maxLength,
      captchaCode: registration.properties?.captcha_code?.maxLength,
    },
    {
      usernameMin: 2,
      usernameMax: 64,
      passwordMin: 6,
      passwordMax: 64,
      inviteCodeMax: 16,
      captchaKey: 64,
      captchaCode: 6,
    },
  );
  assert.equal(registration.required?.includes("invite_code") ?? false, false);
  assert.ok(operation("/api/auth/register", "post").responses?.["413"]);
  operation("/api/auth/kai/status", "get");
  assert.ok(bodySchema("/api/auth/kai/bind/start", "post").properties?.return_url);
  assert.deepEqual(bodySchema("/api/auth/kai/bind/exchange", "post").required, ["ticket"]);
});

test("hourly order and Qixiang recharge operations match the canonical backend", () => {
  const create = bodySchema("/api/orders", "post");
  const renew = bodySchema("/api/orders/{oid}/renew", "post");
  assert.ok(create.properties?.hours);
  assert.ok(create.properties?.client_request_id);
  assert.ok(renew.properties?.hours);
  assert.ok(renew.required?.includes("client_request_id"));
  for (const [path, method] of [
    ["/api/payments/qixiang/config", "get"],
    ["/api/payments/qixiang/recharge-orders", "post"],
    ["/api/payments/qixiang/orders", "get"],
    ["/api/payments/qixiang/orders/{order_no}", "get"],
    ["/api/payments/qixiang/orders/{order_no}/query", "post"],
    ["/api/payments/qixiang/orders/{order_no}/cancel", "post"],
    ["/api/payments/qixiang/checkout/{token}", "get"],
  ] as const) operation(path, method);
});

test("buy-request creation exposes a backwards-compatible retry key", () => {
  const create = bodySchema("/api/buy-requests", "post");
  assert.ok(create.properties?.client_request_id);
  assert.equal(create.required?.includes("client_request_id") ?? false, false);
  const phone = create.properties?.phone?.anyOf?.find((item) => item.type === "string");
  assert.deepEqual(
    { minLength: phone?.minLength, maxLength: phone?.maxLength, pattern: phone?.pattern },
    { minLength: 6, maxLength: 20, pattern: "^(?:[0-9]{6,20}|\\+[1-9][0-9]{5,14})$" },
  );

  const selectOperation = operation("/api/buy-requests/{request_id}/quotes/{quote_id}/select", "post");
  assert.equal(selectOperation.requestBody?.required ?? false, false);
  const selection = bodySchema("/api/buy-requests/{request_id}/quotes/{quote_id}/select", "post");
  assert.deepEqual(selection.required, ["expected_revision_id"]);
  assert.ok(selection.properties?.expected_revision_id);
});

test("supplier resource edits expose a backwards-compatible version precondition", () => {
  const create = bodySchema("/api/supplier/devices", "post");
  assert.ok(create.properties?.client_request_id);
  assert.equal(create.required?.includes("client_request_id") ?? false, false);
  const update = bodySchema("/api/supplier/devices/{did}", "put");
  assert.ok(update.properties?.expected_version);
  assert.equal(update.required?.includes("expected_version") ?? false, false);
  const deleteParameters = operation("/api/supplier/devices/{did}", "delete").parameters ?? [];
  assert.ok(deleteParameters.some((parameter) => parameter.name === "expected_version"));
});

test("administrator and finance lists expose the platform filter", () => {
  for (const path of ["/api/admin/overview", "/api/admin/users", "/api/admin/orders", "/api/admin/recharge-orders", "/api/finance/verifications", "/api/finance/bank-cards", "/api/finance/withdrawals"]) {
    const names = operation(path, "get").parameters?.map((parameter) => parameter.name) ?? [];
    assert.ok(names.includes("platform"), `${path} must expose the platform filter`);
  }
});
