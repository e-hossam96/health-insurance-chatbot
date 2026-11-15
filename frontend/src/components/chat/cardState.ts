export type CardFailureKind = 'error' | 'slot_taken' | 'not_cancellable';

export type CardSetState = {
  busyId: number | null;
  doneId: number | null;
  failure: { id: number; kind: CardFailureKind } | null;
};

export const INITIAL_CARD_STATE: CardSetState = { busyId: null, doneId: null, failure: null };
