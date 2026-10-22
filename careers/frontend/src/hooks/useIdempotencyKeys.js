import { useCallback, useRef } from "react";

import { createIdempotencyKey } from "../api/idempotency";

export function useIdempotencyKeys() {
  const keysRef = useRef(new Map());

  const getKey = useCallback((actionId) => {
    if (!keysRef.current.has(actionId)) {
      keysRef.current.set(actionId, createIdempotencyKey());
    }
    return keysRef.current.get(actionId);
  }, []);

  const clearKey = useCallback((actionId) => {
    keysRef.current.delete(actionId);
  }, []);

  return { getKey, clearKey };
}
