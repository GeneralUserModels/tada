import { useState, useCallback } from "react";
import {
  getMemoryPages,
  getMemoryPage,
  updateMemoryPage,
  deleteMemoryPage,
  getMemoryStatus,
} from "../api/client";

export interface WikiPage {
  path: string;
  title: string;
  confidence: number | null;
  last_updated: string | null;
  category: string | null;
}

export interface WikiStatus {
  exists: boolean;
  last_ingest: string | null;
  last_lint: string | null;
  page_count: number;
}

export function useMemory() {
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [status, setStatus] = useState<WikiStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [pagesRes, statusRes] = await Promise.all([
      getMemoryPages(),
      getMemoryStatus(),
    ]);
    setPages(pagesRes as WikiPage[]);
    setStatus(statusRes as WikiStatus);
    setLoading(false);
  }, []);

  const getPage = useCallback(async (path: string): Promise<string> => {
    return getMemoryPage(path);
  }, []);

  const savePage = useCallback(async (path: string, content: string) => {
    await updateMemoryPage(path, content);
  }, []);

  const deletePage = useCallback(async (path: string) => {
    await deleteMemoryPage(path);
  }, []);

  return { pages, status, loading, load, getPage, savePage, deletePage };
}
