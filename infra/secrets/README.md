# Production secret files

Create `infra/secrets/runtime/` on the deployment host. The directory is ignored by Git. Each file must contain only the corresponding value, without labels or quotes.

Required files:

- `postgres_password`
- `redis_password`
- `app_secret_key` (at least 32 random characters)
- `payout_encryption_key` (at least 32 random characters)
- `kyc_encryption_key` (at least 32 random characters)
- `getdeploying_api_key` (active GetDeploying API subscription key)
- `pingxx_api_key` (`sk_live_...` in production, `sk_test_...` for local simulation)
- `pingxx_merchant_private_key.pem`
- `pingxx_public_key.pem` (the Ping++ platform public key used for Webhook verification)
- `smtp_password`

Never commit the `runtime/` directory. Back up the three application encryption keys in a separate secret manager; losing them makes sessions, payout details, or KYC identity fields unusable.
