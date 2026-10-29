import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { ApiError } from "../lib/api";
import { job } from "../test/fixtures";
import { renderAt } from "../test/render";
import { ListingsPage, PAGE_SIZE, queryFromParams } from "./Listings";

vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), api: { jobs: vi.fn(), me: vi.fn() } }));
const jobs = vi.mocked(api.jobs);

function Where() {
  const l = useLocation();
  return <span data-testid="url">{l.search}</span>;
}
const page = () => renderAt(<><Routes><Route path="/" element={<ListingsPage />} /></Routes><Where /></>, "/", { auth: false });

beforeEach(() => jobs.mockReset());

it("defaults to India + remote and shows loading then results with the total", async () => {
  jobs.mockResolvedValue({ jobs: [job({ id: 1 }), job({ id: 2, title: "Data Analyst", company_name: "Globex" })], total: 2 });
  page();
  expect(screen.getByRole("status")).toHaveTextContent("Loading jobs");
  expect(await screen.findByText("Data Analyst")).toBeInTheDocument();
  expect(screen.getByText("2 jobs")).toBeInTheDocument();
  expect(jobs).toHaveBeenCalledWith(expect.objectContaining({ scope: "india_remote", sort: "newest", limit: PAGE_SIZE, offset: 0 }));
  expect(screen.getByLabelText("Where")).toHaveValue("india_remote");
});

it("links each card to its detail page and shows freshness", async () => {
  jobs.mockResolvedValue({ jobs: [job({ id: 7 })], total: 1 });
  page();
  expect(await screen.findByRole("link", { name: "Python Developer" })).toHaveAttribute("href", "/jobs/7");
  expect(screen.getByText(/Last checked/)).toBeInTheDocument();
});

it("each card has an Apply button that opens the original posting, and never a javascript: link", async () => {
  jobs.mockResolvedValue({ jobs: [job({ id: 1 }), job({ id: 2, title: "Bad Link", apply_url: "javascript:alert(1)" })], total: 2 });
  page();
  const apply = await screen.findByRole("link", { name: /Apply for Python Developer at Acme Corp/ });
  expect(apply).toHaveAttribute("href", "https://acme.example/jobs/1");
  expect(apply).toHaveAttribute("target", "_blank");
  expect(apply).toHaveAttribute("rel", expect.stringContaining("noopener"));
  expect(screen.queryByRole("link", { name: /Apply for Bad Link/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Details for Bad Link" })).toHaveAttribute("href", "/jobs/2");
});

it("shows a helpful empty state", async () => {
  jobs.mockResolvedValue({ jobs: [], total: 0 });
  page();
  expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
  expect(screen.getByText("No jobs")).toBeInTheDocument();
});

it("shows the error and retries", async () => {
  jobs.mockRejectedValueOnce(new ApiError(500, "The server had a problem. Please try again."));
  jobs.mockResolvedValueOnce({ jobs: [job()], total: 1 });
  page();
  expect(await screen.findByRole("alert")).toHaveTextContent("The server had a problem");
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Python Developer")).toBeInTheDocument();
  expect(jobs).toHaveBeenCalledTimes(2);
});

it("puts filters in the URL and queries the API with them", async () => {
  jobs.mockResolvedValue({ jobs: [job()], total: 1 });
  page();
  await screen.findByText("Python Developer");
  await userEvent.type(screen.getByLabelText("Search"), "backend");
  await userEvent.type(screen.getByLabelText("Skill"), "python");
  await userEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ q: "backend", skill: "python" })));
  expect(screen.getByTestId("url").textContent).toContain("q=backend");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "internship");
  await waitFor(() => expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ job_type: "internship", q: "backend" })));
  await userEvent.click(screen.getByLabelText("Hide closed"));
  await waitFor(() => expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ hide_expired: true })));
});

it("the category row filters by job type and shows which one is selected", async () => {
  jobs.mockResolvedValue({ jobs: [job()], total: 1 });
  page();
  await screen.findByText("Python Developer");
  const row = screen.getByRole("group", { name: "Job type" });
  expect(within(row).getByRole("button", { name: "All jobs" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(within(row).getByRole("button", { name: "Internships" }));
  await waitFor(() => expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ job_type: "internship" })));
  expect(within(row).getByRole("button", { name: "Internships" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Type")).toHaveValue("internship");
});

it("changing a filter goes back to page 1, and clear filters resets", async () => {
  jobs.mockResolvedValue({ jobs: [job()], total: 100 });
  renderAt(<><Routes><Route path="/" element={<ListingsPage />} /></Routes><Where /></>, "/?page=3&q=x", { auth: false });
  await screen.findByText("Python Developer");
  expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 2 * PAGE_SIZE, q: "x" }));
  await userEvent.selectOptions(screen.getByLabelText("Sort"), "title");
  await waitFor(() => expect(screen.getByTestId("url").textContent).not.toContain("page="));
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("?scope=india_remote"));
});

it("paginates", async () => {
  jobs.mockResolvedValue({ jobs: [job()], total: 45 });
  page();
  await screen.findByText("Python Developer");
  const nav = screen.getByRole("navigation", { name: "Pagination" });
  expect(within(nav).getByText(/1–20 of 45 · page 1 of 3/)).toBeInTheDocument();
  expect(within(nav).getByRole("button", { name: /Previous/ })).toBeDisabled();
  await userEvent.click(within(nav).getByRole("button", { name: /Next/ }));
  await waitFor(() => expect(jobs).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 })));
});

it("hides pagination when everything fits on one page", async () => {
  jobs.mockResolvedValue({ jobs: [job()], total: 5 });
  page();
  await screen.findByText("Python Developer");
  expect(screen.queryByRole("navigation", { name: "Pagination" })).not.toBeInTheDocument();
});

describe("queryFromParams", () => {
  it("parses and defaults", () => {
    const q = queryFromParams(new URLSearchParams("page=2&grad_year=2026&hide_expired=1&sort=title"));
    expect(q).toMatchObject({ page: 2, offset: PAGE_SIZE, grad_year: 2026, hide_expired: true, sort: "title", scope: "india_remote" });
    expect(queryFromParams(new URLSearchParams("page=-4&grad_year=abc"))).toMatchObject({ page: 1, grad_year: undefined });
  });
});


/** A minimal matchMedia: `narrow` answers every max-width query. */
function fakeMatchMedia(narrow: boolean): typeof window.matchMedia {
  return ((query: string) => ({ matches: narrow && query.includes("max-width"), media: query, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
}

describe("filters on a phone", () => {
  const original = window.matchMedia;
  afterEach(() => { window.matchMedia = original; });

  it("start collapsed on a narrow screen and open on a wide one", async () => {
    jobs.mockResolvedValue({ jobs: [job()], total: 1 });
    window.matchMedia = fakeMatchMedia(true);
    const narrow = page();
    await screen.findByText("Python Developer");
    expect(narrow.container.querySelector("details")).not.toHaveAttribute("open");
    narrow.unmount();
    window.matchMedia = fakeMatchMedia(false);
    const wide = page();
    await screen.findByText("Python Developer");
    expect(wide.container.querySelector("details")).toHaveAttribute("open");
  });

  it("says when filters are active", async () => {
    jobs.mockResolvedValue({ jobs: [], total: 0 });
    renderAt(<Routes><Route path="/" element={<ListingsPage />} /></Routes>, "/?q=python", { auth: false });
    expect(await screen.findByText("Filters (active)")).toBeInTheDocument();
  });
});
