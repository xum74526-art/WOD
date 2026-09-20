# Commerce modes

KAI星算 ships one codebase with two independently controlled release modes. The
default review build is a matchmaking product. A separately reviewed qualified
build can enable direct wallet transactions without restoring deleted code.

## Review / matchmaking release

Server configuration:

```dotenv
MATCHMAKING_ENABLED=true
DIRECT_TRADE_ENABLED=false
PAYMENT_SERVICE_ENABLED=false
MANUAL_BANK_CARD_ENABLED=false
MANUAL_PAYOUT_ENABLED=false
MAPAY_ENABLED=false
MAPAY_LEGACY_RECONCILIATION_ENABLED=false
QIXIANGPAY_ENABLED=false
QIXIANGPAY_REFUND_ENABLED=false
PAYMENT_RECONCILIATION_ENABLED=false
```

Android and iOS build configuration:

```dotenv
VITE_ENABLE_DIRECT_TRADE=false
```

This mode keeps market information, charts, product details, request
submission, merchant quotes, buyer cooperation intent, platform coordination,
and historical account records. It does not create new paid orders, freeze
wallet balances, create recharge orders, or accept new withdrawal requests.

## Qualified direct-transaction release

1. Keep `MATCHMAKING_ENABLED=true` so older review binaries can continue using
   the request workflow.
2. Enable `DIRECT_TRADE_ENABLED=true` on the API only after the required
   qualifications and operating procedures are ready.
3. Configure `QIXIANGPAY_ENABLED=true` for historical query/callback close-out,
   then enable `QIXIANGPAY_REFUND_ENABLED` and
   `PAYMENT_RECONCILIATION_ENABLED` only after those paths pass provider
   verification. `PAYMENT_SERVICE_ENABLED` is the separate switch that permits
   new collection. The first qualified release uses QiXiang Pay only, keeps
   `MAPAY_ENABLED=false`, and uses the dedicated return URL
   `https://wod.kai.com/payment/qixiang/return`.
4. Enable bank-card registration and payout separately with
   `MANUAL_BANK_CARD_ENABLED` and `MANUAL_PAYOUT_ENABLED`.
5. Produce a new Android/iOS binary with `VITE_ENABLE_DIRECT_TRADE=true` and
   submit that binary for the appropriate review. A server flag alone cannot
   expose direct transactions in an existing review build.
6. Keep `REVENUE_SETTLEMENT_ENABLED=false` unless the independent synthetic-
   compute revenue writer has separately been approved; normal settled merchant
   sale income and manual payout do not require it.

Direct transaction UI is exposed only when both the mobile build gate and the
server capability are explicitly true. Missing, malformed, or unreachable
capability responses fail closed.

The QiXiang HTTPS return only closes the hosted checkout and asks the client to
query the server. Return-page query parameters, redirects, and client messages
are never proof of payment; signed notification, active provider query, and the
server ledger are authoritative. The payment return must not reuse the KAI
OAuth `kai://auth` scheme.

## Runtime contract

Clients read `GET /api/platform/capabilities`. The response declares the
effective commerce mode and the separately effective payment, recharge,
withdrawal, matchmaking, and history-read capabilities. Product responses also
declare `interaction_mode` and `inquiry_available`; `purchasable` is always
false while direct trade is disabled.

Disabling direct trade blocks new financial commitments. Existing order,
payment, dispute, cancellation, callback, and payout-review records remain
available for reconciliation and safe operational close-out. To stop only new
recharges, disable `PAYMENT_SERVICE_ENABLED` while keeping the QiXiang provider,
refund, and reconciliation switches configured until every in-flight item has
reached a reviewed terminal state.
