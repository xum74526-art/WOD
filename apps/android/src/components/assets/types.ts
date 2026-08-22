export type AssetPanelKey =
  | 'asset-overview'
  | 'compute-assets'
  | 'device-hosting'
  | 'device-status'
  | 'hosting-earnings'
  | 'action-required'
  | 'expiry-maintenance'

export interface AssetPanelOption {
  key: AssetPanelKey
  label: string
}
