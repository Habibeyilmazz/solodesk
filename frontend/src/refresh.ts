import { createContext, useContext } from "react";

export const RefreshContext = createContext({ version: 0, bump: () => {} });

/** `version` goes into a page's load dependencies; `bump()` after any change refetches them all. */
export function useRefresh() {
  return useContext(RefreshContext);
}
