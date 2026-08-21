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
}
export function getAddresses() { return request<AddressItem[]>({ url: '/addresses' }) }
export function addAddress(data: Partial<AddressItem>) { return request<AddressItem>({ url: '/addresses', method: 'POST', data }) }
export function updateAddress(id: number, data: Partial<AddressItem>) { return request<AddressItem>({ url: `/addresses/${id}`, method: 'PUT', data }) }
export function setDefaultAddress(id: number) { return request({ url: `/addresses/${id}/default`, method: 'POST' }) }
export function deleteAddress(id: number) { return request({ url: `/addresses/${id}`, method: 'DELETE' }) }
