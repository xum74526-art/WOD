import { request } from './request'

export interface AddressItem {
  id: number
  name: string
  phone: string
  province: string
  city: string
  district: string
  detail: string
  label: string | null
  is_default: boolean
  version?: number
}

interface CanonicalAddress {
  id: number
  label: string
  recipient_name: string
  phone: string
  province: string
  city: string
  district?: string | null
  address_line: string
  is_default: boolean
  version: number
}

function toAddress(row: CanonicalAddress): AddressItem {
  return {
    id: row.id,
    name: row.recipient_name,
    phone: row.phone,
    province: row.province,
    city: row.city,
    district: row.district || '',
    detail: row.address_line,
    label: row.label,
    is_default: row.is_default,
    version: row.version,
  }
}

function toCanonical(data: Partial<AddressItem>) {
  return {
    label: data.label || '常用地址',
    recipient_name: data.name,
    phone: data.phone,
    province: data.province,
    city: data.city,
    district: data.district || undefined,
    address_line: data.detail,
    is_default: data.is_default,
  }
}

export function getAddresses() {
  return request<CanonicalAddress[]>({ url: '/account/addresses' }).then(rows => rows.map(toAddress))
}
export function addAddress(data: Partial<AddressItem>) {
  return request<CanonicalAddress>({ url: '/account/addresses', method: 'POST', data: toCanonical(data) }).then(toAddress)
}
export function updateAddress(id: number, data: Partial<AddressItem>) {
  return request<CanonicalAddress>({
    url: `/account/addresses/${id}`,
    method: 'PATCH',
    data: { ...toCanonical(data), version: data.version || 1 },
  }).then(toAddress)
}
export function setDefaultAddress(id: number) {
  return request<CanonicalAddress>({ url: `/account/addresses/${id}/default`, method: 'POST' }).then(toAddress)
}
export function deleteAddress(id: number) {
  return request({ url: `/account/addresses/${id}`, method: 'DELETE' })
}
