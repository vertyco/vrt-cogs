// Type hints for ActivityHub's page helper, for your editor. Copy this file next to your game.js and put
// /// <reference path="activityhub.d.ts" /> at the top of game.js. Only your editor reads it, never the browser.
declare module "activityhub" {
  /** The error hub.api() and hub.socket() throw. */
  export class HubError extends Error {
    /** 400 for your own {"error"} replies, the HTTP status for the hub's other errors, the close code for live connections, 0 offline or when the bot couldn't be reached. */
    status: number;
  }

  export interface HubPlayer {
    id: string;
    username: string;
    displayName: string;
    avatar: string;
    guildId: string | null;
    guildName: string | null;
    guildIcon: string | null;
  }

  export interface HubPerson {
    id: string;
    name: string;
    avatar: string;
    game: string | null;
    gameName: string | null;
    status: string;
    data: unknown;
    busy: boolean;
    away: boolean;
    you: boolean;
    here: boolean;
  }

  /** A live connection, page side. */
  export interface HubConnection {
    /** The latest round trip to the bot and back in milliseconds, or null before the first one and while reconnecting. */
    readonly latency: number | null;
    /** Returns false without sending while the helper reconnects or after the connection closed. */
    send(data: unknown): boolean;
    on(handler: (data: any) => void): void;
    onClose(handler: (code: number) => void): void;
    onReconnecting(handler: (code: number) => void): void;
    onReconnected(handler: () => void): void;
    close(): void;
  }

  export interface Hub {
    readonly offline: boolean;
    /** "desktop" (Discord's computer app or a browser) or "mobile" (its phone and tablet app). null in the preview. */
    readonly platform: "desktop" | "mobile" | null;
    readonly player: HubPlayer | null;
    /** Discord's Embedded App SDK object, or null outside Discord. */
    readonly discord: any;
    readonly follow: { id: string; name: string } | null;
    /** Everyone in the window, the player included. A new array on each read. */
    readonly people: HubPerson[];
    /** Calls your action `name` with `data`. */
    api(
      name: string,
      data?: object,
      options?: {
        /** The request still reaches the bot after the page is gone, for a save on pagehide. At most 64 KB. */
        keepalive?: boolean;
      },
    ): Promise<any>;
    fetch(path: string, options?: RequestInit): Promise<Response>;
    socket(): Promise<HubConnection>;
    stat(text: string): void;
    status(text: string, data?: unknown): void;
    busy(on: boolean): void;
    /** Returns a function that stops it. */
    onPeople(fn: (people: HubPerson[]) => void): () => void;
    peopleButton(): HTMLElement;
    openPeople(): void;
    backToMenu(): void;
  }

  export function connect(): Promise<Hub>;
  export function backToMenu(): void;
}
