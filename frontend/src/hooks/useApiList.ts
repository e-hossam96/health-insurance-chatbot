import { useCallback, useEffect, useState } from 'react';

export function useApiList<T>(fetcher: () => Promise<T[]>): {
  items: T[];
  loading: boolean;
  reload: () => void;
} {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    fetcher()
      .then(setItems)
      .finally(() => setLoading(false));
  }, [fetcher]);
  useEffect(load, [load]);
  return { items, loading, reload: load };
}
