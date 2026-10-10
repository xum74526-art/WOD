import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

type SchemaReference = { $ref?: string; anyOf?: SchemaReference[] };
type Operation = { parameters?: Array<{ name: string }>; requestBody?: { required?: boolean; content?: { "application/json"?: { schema?: SchemaReference } } }; responses?: Record<string, unknown> };
type PropertySchema = { type?: string; minLength?: number; maxLength?: number; pattern?: string; enum?: string[]; anyOf?: PropertySchema[] };
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
  assert.deepEqual(create.properties?.purchase_type?.enum, ["usage", "holding"]);
  assert.equal(create.required?.includes("purchase_type") ?? false, false);
  assert.ok(renew.properties?.hours);
  assert.ok(renew.required?.includes("client_request_id"));
  for (const [path, method] of [
    ["/api/payments/qixiang/config", "get"],
    ["/api/payments/qixiang/recharge-orders", "post"],
    ["/api/payments/qixiang/orders", "get"],
    ["/api/payments/qixiang/orders/{order_no}", "get"],
    ["/api/payments/qixiang/orders/{order_no}/query", "post"],
    ["/api/payments/qixiang/orders/{order_no}/cancel", "post"],
    ["/api/payments/qixiang/orders/{order_no}/refund-request", "get"],
    ["/api/payments/qixiang/orders/{order_no}/refund-requests", "post"],
    ["/api/payments/qixiang/refund-requests", "get"],
    ["/api/payments/qixiang/checkout/{token}", "get"],
  ] as const) operation(path, method);
  const recharge = bodySchema("/api/payments/qixiang/recharge-orders", "post");
  const rechargeRequestId = recharge.properties?.client_request_id?.anyOf?.find((item) => item.type === "string");
  assert.deepEqual(
    { minLength: rechargeRequestId?.minLength, maxLength: rechargeRequestId?.maxLength, pattern: rechargeRequestId?.pattern },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );
  assert.equal(recharge.required?.includes("client_request_id") ?? false, false);
  const refundRequest = bodySchema("/api/payments/qixiang/orders/{order_no}/refund-requests", "post");
  assert.deepEqual(refundRequest.required, ["client_request_id", "reason"]);
  assert.equal(refundRequest.properties?.reason?.minLength, 5);
  assert.deepEqual(
    {
      minLength: refundRequest.properties?.client_request_id?.minLength,
      maxLength: refundRequest.properties?.client_request_id?.maxLength,
      pattern: refundRequest.properties?.client_request_id?.pattern,
    },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );
  assert.equal(contract.paths["/api/payments/mapay/recharge-orders"]?.post, undefined);
  assert.equal(contract.paths["/api/payments/mapay/checkout/{token}"]?.get, undefined);
});

test("holding assets require an idempotent, price-confirmed sale request", () => {
  const sale = bodySchema("/api/assets/{aid}/sell", "post");
  assert.deepEqual(sale.required, ["client_request_id", "expected_unit_price_card_hours"]);
  assert.deepEqual(
    {
      minLength: sale.properties?.client_request_id?.minLength,
      maxLength: sale.properties?.client_request_id?.maxLength,
      pattern: sale.properties?.client_request_id?.pattern,
    },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );
  assert.ok(sale.properties?.expected_unit_price_card_hours);
});

test("administrator payment operations match the canonical backend", () => {
  for (const [path, method] of [
    ["/api/admin/recharge-orders", "get"],
    ["/api/admin/recharge-orders/{payment_order_id}", "get"],
    ["/api/admin/recharge-orders/{payment_order_id}/review", "post"],
    ["/api/admin/recharge-orders/{payment_order_id}/refunds", "post"],
    ["/api/admin/payment-refunds", "get"],
    ["/api/admin/payment-refunds/{refund_id}", "get"],
    ["/api/admin/payment-refunds/{refund_id}/resolve", "post"],
    ["/api/admin/payment-refund-requests", "get"],
    ["/api/admin/payment-refund-requests/{request_id}", "get"],
    ["/api/admin/payment-refund-requests/{request_id}/review", "post"],
  ] as const) operation(path, method);

  const review = bodySchema("/api/admin/recharge-orders/{payment_order_id}/review", "post");
  assert.deepEqual(review.required, ["action", "note"]);
  const reviewRequestId = review.properties?.client_request_id?.anyOf?.find((item) => item.type === "string");
  assert.deepEqual(
    { minLength: reviewRequestId?.minLength, maxLength: reviewRequestId?.maxLength, pattern: reviewRequestId?.pattern },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );

  const refund = bodySchema("/api/admin/recharge-orders/{payment_order_id}/refunds", "post");
  assert.deepEqual(refund.required, ["client_request_id", "reason"]);
  assert.deepEqual(
    {
      minLength: refund.properties?.client_request_id?.minLength,
      maxLength: refund.properties?.client_request_id?.maxLength,
      pattern: refund.properties?.client_request_id?.pattern,
    },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );

  const resolution = bodySchema("/api/admin/payment-refunds/{refund_id}/resolve", "post");
  assert.deepEqual(resolution.required, ["outcome", "note"]);
  assert.equal(resolution.properties?.client_request_id, undefined);

  const requestReview = bodySchema("/api/admin/payment-refund-requests/{request_id}/review", "post");
  assert.deepEqual(requestReview.required, ["action", "note"]);
  assert.deepEqual(requestReview.properties?.action?.enum, ["approve", "reject"]);
  assert.deepEqual(
    { minLength: requestReview.properties?.note?.minLength, maxLength: requestReview.properties?.note?.maxLength },
    { minLength: 3, maxLength: 500 },
  );
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
  for (const path of ["/api/admin/overview", "/api/admin/users", "/api/admin/orders", "/api/admin/recharge-orders", "/api/admin/payment-refund-requests", "/api/finance/verifications", "/api/finance/bank-cards", "/api/finance/withdrawals"]) {
    const names = operation(path, "get").parameters?.map((parameter) => parameter.name) ?? [];
    assert.ok(names.includes("platform"), `${path} must expose the platform filter`);
  }
});

test("administrator account actions are explicit, audited, and idempotent", () => {
  const action = bodySchema("/api/admin/users/{user_id}/actions", "post");
  assert.deepEqual(action.properties?.action?.enum, [
    "send_password_reset",
    "issue_password_reset_code",
    "freeze",
    "unfreeze",
    "delete",
  ]);
  assert.deepEqual(action.required, ["action", "client_request_id", "reason"]);
  assert.deepEqual(
    {
      minLength: action.properties?.client_request_id?.minLength,
      maxLength: action.properties?.client_request_id?.maxLength,
      pattern: action.properties?.client_request_id?.pattern,
    },
    { minLength: 12, maxLength: 64, pattern: "^[A-Za-z0-9._:-]+$" },
  );
  assert.deepEqual(
    { minLength: action.properties?.reason?.minLength, maxLength: action.properties?.reason?.maxLength },
    { minLength: 4, maxLength: 500 },
  );

  const historyNames = operation("/api/admin/users/{user_id}/actions", "get").parameters?.map((parameter) => parameter.name) ?? [];
  assert.ok(historyNames.includes("page"));
  assert.ok(historyNames.includes("page_size"));
});

test("administrator support and merchant controls are explicit canonical contracts", () => {
  const support = bodySchema("/api/admin/support-tickets/{ticket_id}/actions", "post");
  assert.deepEqual(support.properties?.action?.enum, ["claim", "assign", "reply", "resolve", "close", "reopen"]);
  assert.deepEqual(support.required, ["action", "expected_status", "request_id"]);

  const supplier = bodySchema("/api/supplier/admin/suppliers/{supplier_id}/status", "post");
  assert.deepEqual(supplier.properties?.action?.enum, ["suspend", "reactivate"]);
  assert.deepEqual(supplier.required, ["action", "expected_status", "reason"]);

  const product = bodySchema("/api/supplier/admin/products/{product_id}/status", "post");
  assert.deepEqual(product.properties?.status?.enum, ["on", "off"]);
  assert.deepEqual(product.required, ["status", "expected_version", "reason"]);

  const auditParameters = operation("/api/finance/audit-logs", "get").parameters?.map((parameter) => parameter.name) ?? [];
  for (const name of ["action_filter", "actor_user_id", "object_type", "object_id", "created_from", "created_to", "page", "page_size"]) {
    assert.ok(auditParameters.includes(name), `audit log must expose ${name}`);
  }
});
