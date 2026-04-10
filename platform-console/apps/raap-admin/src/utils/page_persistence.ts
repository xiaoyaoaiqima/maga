import type { WatchSource, WatchStopHandle } from 'vue';

import { ref, watch } from 'vue';

type PersistEnvelope<TData> = {
  data: TData;
  version: number;
};

type UsePagePersistenceParams<TData> = {
  apply_state: (data: TData) => Promise<void> | void;
  debounce_ms?: number;
  get_state: () => TData;
  storage_key: string;
  version: number;
};

type RestoreParams = {
  /**
   * 有些页面需要先拉完列表数据才能把 id 映射回 record；
   * 这时可以把 restore 放到 fetch 之后调用。
   */
  should_restore?: boolean;
};

export function use_page_persistence<TData extends Record<string, any>>(
  params: UsePagePersistenceParams<TData>,
) {
  const is_restoring = ref(false);
  const debounce_ms = params.debounce_ms ?? 250;

  let timer: null | number = null;
  let stop: null | WatchStopHandle = null;

  function read(): null | TData {
    try {
      const raw = localStorage.getItem(params.storage_key);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as null | PersistEnvelope<TData>;
      if (!parsed) return null;
      if (parsed.version !== params.version) return null;
      return parsed.data ?? null;
    } catch {
      return null;
    }
  }

  function write(data: TData) {
    try {
      const payload: PersistEnvelope<TData> = {
        version: params.version,
        data,
      };
      localStorage.setItem(params.storage_key, JSON.stringify(payload));
    } catch {
      // localStorage 写入失败不影响主流程
    }
  }

  function clear() {
    try {
      localStorage.removeItem(params.storage_key);
    } catch {
      // ignore
    }
  }

  function schedule_write() {
    if (is_restoring.value) return;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      write(params.get_state());
      timer = null;
    }, debounce_ms);
  }

  function start_auto_persist(watch_source?: WatchSource<unknown>) {
    stop?.();
    stop = watch(
      watch_source ?? (() => params.get_state()),
      () => schedule_write(),
      {
        deep: true,
      },
    );
  }

  async function restore(
    restore_params?: RestoreParams,
  ): Promise<null | TData> {
    const should_restore = restore_params?.should_restore ?? true;
    if (!should_restore) return null;

    const persisted = read();
    if (!persisted) return null;

    is_restoring.value = true;
    try {
      await params.apply_state(persisted);
      return persisted;
    } finally {
      is_restoring.value = false;
    }
  }

  return {
    is_restoring,
    read,
    write,
    clear,
    restore,
    start_auto_persist,
  };
}
