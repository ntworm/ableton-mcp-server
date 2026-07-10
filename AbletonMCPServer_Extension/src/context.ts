import { type initialize } from '@ableton-extensions/sdk';

export type ExtensionContext = ReturnType<typeof initialize>;

let extensionContext: ExtensionContext | null = null;

export function getExtensionContext(): ExtensionContext | null {
  return extensionContext;
}

export function setExtensionContext(ctx: ExtensionContext): void {
  extensionContext = ctx;
}

export function clearExtensionContext(): void {
  extensionContext = null;
}
