import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThemeProvider, THEME_STORAGE_KEY, useTheme } from "./ThemeContext";
import { ThemeToggle } from "./ThemeToggle";

function mockSystemTheme(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-color-scheme: dark)" && dark,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

function Harness() {
  const { theme } = useTheme();
  return (
    <>
      <output aria-label="Current theme">{theme}</output>
      <ThemeToggle />
    </>
  );
}

function renderTheme() {
  return render(
    <ThemeProvider>
      <Harness />
    </ThemeProvider>,
  );
}

describe("ThemeProvider", () => {
  it.each([
    { dark: false, expected: "light" },
    { dark: true, expected: "dark" },
  ] as const)("uses the system preference when no choice is saved", ({ dark, expected }) => {
    mockSystemTheme(dark);
    renderTheme();

    expect(screen.getByLabelText("Current theme")).toHaveTextContent(expected);
    expect(document.documentElement).toHaveAttribute("data-theme", expected);
  });

  it("restores a saved preference instead of the system preference", () => {
    mockSystemTheme(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderTheme();

    expect(screen.getByLabelText("Current theme")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("switches light to dark and persists the choice", async () => {
    mockSystemTheme(false);
    const user = userEvent.setup();
    renderTheme();

    const toggle = screen.getByRole("button", { name: "Switch to dark theme" });
    await user.click(toggle);

    expect(screen.getByLabelText("Current theme")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
  });

  it("switches dark to light", async () => {
    mockSystemTheme(true);
    const user = userEvent.setup();
    renderTheme();

    await user.click(screen.getByRole("button", { name: "Switch to light theme" }));

    expect(screen.getByLabelText("Current theme")).toHaveTextContent("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("restores the selected theme after a remount", async () => {
    mockSystemTheme(false);
    const user = userEvent.setup();
    const first = renderTheme();
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    first.unmount();

    renderTheme();

    expect(screen.getByLabelText("Current theme")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("exposes an accessible native button that works from the keyboard", async () => {
    mockSystemTheme(false);
    const user = userEvent.setup();
    renderTheme();

    const toggle = screen.getByRole("button", { name: "Switch to dark theme" });
    toggle.focus();
    await user.keyboard("{Enter}");

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(toggle).toHaveAttribute("type", "button");
  });
});
