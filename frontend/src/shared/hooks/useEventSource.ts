import { useEffect, useRef } from "react";

interface TypedEvent {
  type: string;
}

export function parseSsePayload<T extends TypedEvent>(eventName: string, rawData: string): T | null {
  try {
    const parsed: unknown = JSON.parse(rawData);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    const payload = parsed as Record<string, unknown>;
    const type = typeof payload.type === "string" ? payload.type : eventName === "message" ? undefined : eventName;
    if (!type) return null;
    return { ...payload, type } as T;
  } catch {
    return null;
  }
}

export function useEventSource<T extends TypedEvent>({
  url,
  eventNames,
  enabled = true,
  onEvent,
  onOpen,
}: {
  url: string;
  eventNames: readonly string[];
  enabled?: boolean;
  onEvent: (event: T) => void;
  onOpen?: () => void;
}) {
  const eventHandler = useRef(onEvent);
  const openHandler = useRef(onOpen);
  eventHandler.current = onEvent;
  openHandler.current = onOpen;
  const eventKey = eventNames.join("|");

  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource(url, { withCredentials: true });
    const dispatch = (eventName: string, event: Event) => {
      if (!(event instanceof MessageEvent) || typeof event.data !== "string") return;
      const parsed = parseSsePayload<T>(eventName, event.data);
      if (parsed) eventHandler.current(parsed);
    };
    const defaultHandler = (event: MessageEvent<string>) => dispatch("message", event);
    const namedHandlers = eventNames.map((eventName) => {
      const handler: EventListener = (event) => dispatch(eventName, event);
      source.addEventListener(eventName, handler);
      return { eventName, handler };
    });

    source.onmessage = defaultHandler;
    source.onopen = () => openHandler.current?.();
    // Native EventSource owns reconnect/backoff. Transport errors intentionally do not close it.
    return () => {
      source.onmessage = null;
      source.onopen = null;
      namedHandlers.forEach(({ eventName, handler }) => source.removeEventListener(eventName, handler));
      source.close();
    };
  }, [enabled, eventKey, url, eventNames]);
}
