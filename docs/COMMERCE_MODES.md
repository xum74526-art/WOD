# Commerce modes

WOD ships one codebase with two independently controlled release modes. The
current App Store review build is a matchmaking product. The future qualified
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
QIXIANGPAY_ENABLED=false
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
3. Enable `PAYMENT_SERVICE_ENABLED` and exactly one configured collection
   provider only after its callback, signature, expiry, reconciliation, and
   refund paths have passed production verification.
4. Enable bank-card registration and payout separately with
   `MANUAL_BANK_CARD_ENABLED` and `MANUAL_PAYOUT_ENABLED`.
5. Produce a new Android/iOS binary with `VITE_ENABLE_DIRECT_TRADE=true` and
   submit that binary for the appropriate review. A server flag alone cannot
   expose direct transactions in an existing review build.

Direct transaction UI is exposed only when both the mobile build gate and the
server capability are explicitly true. Missing, malformed, or unreachable
capability responses fail closed.

## Runtime contract

Clients read `GET /api/platform/capabilities`. The response declares the
effective commerce mode and the separately effective payment, recharge,
withdrawal, matchmaking, and history-read capabilities. Product responses also
declare `interaction_mode` and `inquiry_available`; `purchasable` is always
false while direct trade is disabled.

Disabling direct trade blocks new financial commitments. Existing order,
payment, dispute, cancellation, callback, and payout-review records remain
available for reconciliation and safe operational close-out.
