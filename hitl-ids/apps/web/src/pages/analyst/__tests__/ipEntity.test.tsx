/**
 * The address page, pinned to the demo database's two endpoints: 18.218.115.60, the Web Attack source
 * whose 77 alerts are mostly tier 2 candidates, and 172.31.69.28, the address it talked to.
 *
 * The stubs answer by path, so the test covers what the page does with each answer the API can give:
 * the two entities, a 404 for an address no alert mentions, and a request still in flight. The peer
 * fixture is defined here rather than in `fixtures.ts` because only this page moves between two
 * addresses, and that move is the thing being tested.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../../../api/client";
import type { Session } from "../../../session/SessionContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import { ATTACKER_ENTITY } from "./fixtures";

const ANALYST: Session = { username: "g.ang", role: "security_analyst" };

const ATTACKER = ATTACKER_ENTITY.ip;
const PEER = "172.31.69.28";
const ENTITY_PREFIX = "/api/entities/ip/";

/** `GET /api/entities/ip/172.31.69.28` on the demo database: the Web Attack's destination. */
const PEER_ENTITY: Schemas["EntityIp"] = {
  ip: PEER,
  alerts: 215,
  asSource: 5,
  asDestination: 210,
  flagged: 207,
  firstSeen: "2018-02-14 15:35:49.531500",
  lastSeen: "2018-02-23 19:17:03.720682",
  byQueueClass: { none: 8, tier2_candidate: 207 },
  byAttackCategory: { DDoS: 148, "Web Attack": 59 },
  verdictMix: {},
  topPeers: [
    { value: ATTACKER, count: 69, flagged: 68 },
    { value: "18.218.11.51", count: 19, flagged: 19 },
  ],
  topDestinationPorts: [
    { value: "80", count: 209, flagged: 207 },
    { value: "53", count: 2, flagged: 0 },
  ],
};

/**
 * Serve the two known addresses — `overrides` first — and answer anything else the way the API does
 * when no alert mentions the address.
 */
function stubEntities(overrides: Readonly<Record<string, Schemas["EntityIp"]>> = {}): Request[] {
  const table: Readonly<Record<string, Schemas["EntityIp"]>> = {
    [ATTACKER]: ATTACKER_ENTITY,
    [PEER]: PEER_ENTITY,
    ...overrides,
  };
  return stubFetch((request) => {
    const { pathname } = new URL(request.url);
    if (!pathname.startsWith(ENTITY_PREFIX)) {
      return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${pathname}` } }, 404);
    }
    const ip = decodeURIComponent(pathname.slice(ENTITY_PREFIX.length));
    const entity = table[ip];
    if (entity === undefined) {
      return jsonResponse({ error: { code: "NOT_FOUND", message: `No alert involving IP ${ip}` } }, 404);
    }
    return jsonResponse(entity);
  });
}

/** The card with this title, once the response that fills it has landed. */
async function findCard(title: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { level: 2, name: title });
  const section = heading.closest("section");
  if (section === null) throw new Error(`no section for ${title}`);
  return section;
}

describe("IP entity page", () => {
  it("leads with the address and the corpus's own counts for it", async () => {
    stubEntities();
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    expect(await screen.findByRole("heading", { level: 1, name: ATTACKER })).toBeInTheDocument();

    const summary = await findCard("Summary");
    // 77 twice: every alert involving this address has it as the source, and none as the destination.
    expect(within(summary).getAllByText("77").length).toBe(2);
    expect(within(summary).getByText("76")).toBeInTheDocument();
    expect(within(summary).getByText("0")).toBeInTheDocument();
    expect(within(summary).getByText("2018-02-20 14:34:14")).toBeInTheDocument();
    expect(within(summary).getByText("2018-02-23 19:17:03")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "All alerts for this address" })).toHaveAttribute(
      "href",
      `/analyst/workstation?search=${ATTACKER}`,
    );
  });

  it("follows a recorded peer to that address's own page", async () => {
    const user = userEvent.setup();
    stubEntities();
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    const peers = await findCard("Top peers");
    const peer = within(peers).getByRole("link", { name: PEER });
    expect(peer).toHaveAttribute("href", `/analyst/entities/ip/${PEER}`);

    await user.click(peer);

    expect(await screen.findByRole("heading", { level: 1, name: PEER })).toBeInTheDocument();
    // 215 is the peer's own alert count: waiting for it waits for the second entity, not the first.
    expect(await screen.findByText("215")).toBeInTheDocument();
  });

  it("lists the queue bands in the contract's order, not by count", async () => {
    stubEntities();
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    const bands = await findCard("Queue bands");
    expect(within(bands).getByRole("columnheader", { name: "Band" })).toBeInTheDocument();
    expect(within(bands).getAllByRole("rowheader").map((row) => row.textContent)).toEqual([
      "Tier 2 candidate",
      "Nothing flagged it",
    ]);
  });

  it("orders the attack classes by how many alerts each carries", async () => {
    stubEntities();
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    const classes = await findCard("Attack classes");
    expect(within(classes).getByRole("columnheader", { name: "Class" })).toBeInTheDocument();
    // The fixture lists DDoS first; 59 Web Attack alerts outrank 17 DDoS ones.
    expect(within(classes).getAllByRole("rowheader").map((row) => row.textContent)).toEqual([
      "Web Attack",
      "DDoS",
    ]);
  });

  it("says when no verdict is in force for the address", async () => {
    stubEntities();
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    expect(await screen.findByText("No verdicts recorded for this address")).toBeInTheDocument();
  });

  it("names a verdict by its label, never by the API's key", async () => {
    stubEntities({ [ATTACKER]: { ...ATTACKER_ENTITY, verdictMix: { mark_false_positive: 2 } } });
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    const verdicts = await findCard("Verdicts in force");
    expect(within(verdicts).getByRole("rowheader", { name: "False Positive" })).toBeInTheDocument();
    expect(within(verdicts).queryByText("mark_false_positive")).toBeNull();
  });

  it("shows the API's own words for an address no alert mentions", async () => {
    stubEntities();
    renderApp("/analyst/entities/ip/10.9.9.9", { session: ANALYST });

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("No alert involving IP 10.9.9.9")).toBeInTheDocument();
    expect(within(alert).getByText("NOT_FOUND · HTTP 404")).toBeInTheDocument();
  });

  it("shows a loading state while the entity is in flight", () => {
    stubFetch((request) => {
      const { pathname } = new URL(request.url);
      if (pathname === `${ENTITY_PREFIX}${ATTACKER}`) return new Promise<Response>(() => undefined);
      return jsonResponse({ error: { code: "NOT_FOUND", message: pathname } }, 404);
    });
    renderApp(`/analyst/entities/ip/${ATTACKER}`, { session: ANALYST });

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
