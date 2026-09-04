/** Called only by an explicit tap on the displayed contact number. */
export function callContactPhone() {
  uni.makePhoneCall({ phoneNumber: '+864001082026' })
}
