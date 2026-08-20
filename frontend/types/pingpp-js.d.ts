declare module "pingpp-js" {
  type PingppError = { msg?: string; extra?: string };
  type PaymentResult = "success" | "fail" | "cancel" | "invalid";
  type PingppSdk = {
    createPayment(
      charge: string,
      callback: (result: PaymentResult, error?: PingppError) => void,
    ): void;
  };
  const pingpp: PingppSdk;
  export default pingpp;
}
