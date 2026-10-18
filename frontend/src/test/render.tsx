import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../lib/auth";

export function renderAt(ui: ReactElement, path = "/", { auth = true }: { auth?: boolean } = {}) {
  const tree = <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>;
  return render(auth ? <AuthProvider>{tree}</AuthProvider> : tree);
}
