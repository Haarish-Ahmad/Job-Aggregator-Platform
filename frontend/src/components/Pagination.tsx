export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <nav className="pagination" aria-label="Pagination">
      <button type="button" className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Previous
      </button>
      <span aria-live="polite">
        {first}–{last} of {total} · page {page} of {pages}
      </span>
      <button type="button" className="btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next →
      </button>
    </nav>
  );
}
