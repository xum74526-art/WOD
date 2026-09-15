export const ACCOUNT_REVENUE_RANGE_DAYS = 7

function settleRequest<T>(request: Promise<T>): Promise<PromiseSettledResult<T>> {
  return request.then(
    (value) => ({ status: 'fulfilled', value }),
    (reason: unknown) => ({ status: 'rejected', reason }),
  )
}

export function startAssetDetailRequests<TAsset, TChart>(
  assetRequest: Promise<TAsset>,
  accountRevenueChartRequest: Promise<TChart>,
) {
  return {
    asset: settleRequest(assetRequest),
    accountRevenueChart: settleRequest(accountRevenueChartRequest),
  }
}
