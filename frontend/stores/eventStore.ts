import { create } from "zustand";

const MAX_EVENTS = 200;

export interface EventEntry {
  id: number;
  type: string;
  message: string;
  ts: number;
}

interface EventStore {
  events: EventEntry[];
  nextId: number;
  addEvent: (type: string, message: string, ts?: number) => void;
  clear: () => void;
}

export const useEventStore = create<EventStore>((set) => ({
  events: [],
  nextId: 1,

  addEvent: (type, message, ts) =>
    set((state) => {
      const events = [
        ...state.events,
        { id: state.nextId, type, message, ts: ts ?? Date.now() / 1000 },
      ];
      if (events.length > MAX_EVENTS) events.shift();
      return { events, nextId: state.nextId + 1 };
    }),

  clear: () => set({ events: [], nextId: 1 }),
}));
