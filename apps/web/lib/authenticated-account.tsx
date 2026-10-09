"use client";

import { createContext, useContext } from "react";

export const AuthenticatedAccount = createContext<number | null>(null);
export const useAuthenticatedAccount = () => useContext(AuthenticatedAccount);
