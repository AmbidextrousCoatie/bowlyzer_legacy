import { describe, expect, it } from "vite-plus/test";
import {
  dismissHint,
  isHintDismissed,
  resetHintStorageForTests,
} from "../lib/contextualHintStorage";

describe("ContextualHint storage", () => {
  it("tracks dismissal per hint id", () => {
    resetHintStorageForTests();
    const id = `test-hint-${Date.now()}`;
    expect(isHintDismissed(id)).toBe(false);
    dismissHint(id);
    expect(isHintDismissed(id)).toBe(true);
  });
});
