"""Persistent, conservative transaction storage for Ledger.

SQLite is used as the prototype persistence layer because it is deterministic,
transactional, and requires no external service. Production deployment should
move this interface to a managed database with backups and access controls.

The store never silently overwrites a source transaction. Exact re-deliveries
are idempotent. Conflicting revisions are retained for explicit review.
Reconciliation candidates are suggestions only; a caller must explicitly
confirm a payout-to-bank-deposit link.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3
import uuid

from transaction_integrity import VALID_KINDS, normalize_record


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_cents(amount: Decimal) -> int:
    return int(amount * 100)


def _from_cents(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


def _stored_record(raw: dict) -> dict:
    record = normalize_record(raw)
    stored = {
        "tenant_id": record["tenant_id"],
        "source": record["source"],
        "external_id": record["external_id"],
        "kind": record["kind"],
        "amount_cents": _to_cents(record["amount"]),
        "currency": record["currency"],
    }
    payload = json.dumps(stored, sort_keys=True, separators=(",", ":"))
    stored["fingerprint"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return stored


def _batch_fingerprint(records: list[dict]) -> str:
    # Sorting makes provider retries idempotent even if delivery order changes.
    payload = json.dumps(sorted(r["fingerprint"] for r in records), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LedgerStore:
    """Tenant-scoped persistent store with audit-safe ingestion and reconciliation."""

    def __init__(self, path: str = "ledger.db"):
        self.path = path
        self.conn = sqlite3.connect(path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = FULL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                batch_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                batch_fingerprint TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                conflict_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS transactions (
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                first_batch_id TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, source, external_id),
                FOREIGN KEY (first_batch_id) REFERENCES import_batches(batch_id)
            );

            CREATE TABLE IF NOT EXISTS transaction_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                existing_fingerprint TEXT NOT NULL,
                existing_kind TEXT NOT NULL,
                existing_amount_cents INTEGER NOT NULL,
                existing_currency TEXT NOT NULL,
                incoming_fingerprint TEXT NOT NULL,
                incoming_kind TEXT NOT NULL,
                incoming_amount_cents INTEGER NOT NULL,
                incoming_currency TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                resolution TEXT,
                resolution_note TEXT,
                resolved_at TEXT,
                UNIQUE (batch_id, tenant_id, source, external_id, incoming_fingerprint),
                FOREIGN KEY (batch_id) REFERENCES import_batches(batch_id)
            );

            CREATE TABLE IF NOT EXISTS reconciliation_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                payout_source TEXT NOT NULL,
                payout_external_id TEXT NOT NULL,
                deposit_source TEXT NOT NULL,
                deposit_external_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                note TEXT,
                UNIQUE (tenant_id, payout_source, payout_external_id),
                UNIQUE (tenant_id, deposit_source, deposit_external_id),
                FOREIGN KEY (tenant_id, payout_source, payout_external_id)
                    REFERENCES transactions(tenant_id, source, external_id),
                FOREIGN KEY (tenant_id, deposit_source, deposit_external_id)
                    REFERENCES transactions(tenant_id, source, external_id)
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_tenant_kind
                ON transactions(tenant_id, kind);
            CREATE INDEX IF NOT EXISTS idx_conflicts_tenant_resolution
                ON transaction_conflicts(tenant_id, resolution);
            """
        )
        self.conn.execute("PRAGMA user_version = 1")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LedgerStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _batch_summary(self, batch_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM import_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None

    def ingest(self, records, *, batch_id: str | None = None) -> dict:
        """Persist one provider batch.

        All records are validated before any write. A batch must belong to one
        tenant and one source. Replaying the same batch ID with the same content
        is idempotent. Reusing a batch ID with different content is rejected.
        Conflicting revisions never overwrite the canonical transaction.
        """
        records = list(records)
        if not records:
            raise ValueError("Import batch cannot be empty")
        normalized = [_stored_record(record) for record in records]
        tenants = {record["tenant_id"] for record in normalized}
        sources = {record["source"] for record in normalized}
        if len(tenants) != 1:
            raise ValueError("An import batch must contain exactly one tenant")
        if len(sources) != 1:
            raise ValueError("An import batch must contain exactly one source")

        if batch_id is None:
            batch_id = str(uuid.uuid4())
        if not isinstance(batch_id, str) or not batch_id.strip():
            raise ValueError("batch_id must be a non-empty string")
        batch_id = batch_id.strip()
        fingerprint = _batch_fingerprint(normalized)

        previous = self._batch_summary(batch_id)
        if previous:
            if previous["batch_fingerprint"] != fingerprint:
                raise ValueError("Batch ID already used with different contents")
            previous["replayed"] = True
            return previous

        tenant_id = next(iter(tenants))
        source = next(iter(sources))
        now = _utc_now()
        inserted = duplicates = conflicts = 0

        with self.conn:
            self.conn.execute(
                """INSERT INTO import_batches
                   (batch_id, tenant_id, source, batch_fingerprint, record_count,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'processing', ?)""",
                (batch_id, tenant_id, source, fingerprint, len(normalized), now),
            )

            for record in normalized:
                key = (record["tenant_id"], record["source"], record["external_id"])
                existing = self.conn.execute(
                    """SELECT kind, amount_cents, currency, fingerprint
                       FROM transactions
                       WHERE tenant_id = ? AND source = ? AND external_id = ?""",
                    key,
                ).fetchone()

                if existing is None:
                    self.conn.execute(
                        """INSERT INTO transactions
                           (tenant_id, source, external_id, kind, amount_cents,
                            currency, fingerprint, first_batch_id, first_seen_at,
                            last_seen_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            record["tenant_id"], record["source"], record["external_id"],
                            record["kind"], record["amount_cents"], record["currency"],
                            record["fingerprint"], batch_id, now, now,
                        ),
                    )
                    inserted += 1
                elif existing["fingerprint"] == record["fingerprint"]:
                    self.conn.execute(
                        """UPDATE transactions SET last_seen_at = ?
                           WHERE tenant_id = ? AND source = ? AND external_id = ?""",
                        (now, *key),
                    )
                    duplicates += 1
                else:
                    self.conn.execute(
                        """INSERT OR IGNORE INTO transaction_conflicts
                           (tenant_id, source, external_id, batch_id,
                            existing_fingerprint, existing_kind,
                            existing_amount_cents, existing_currency,
                            incoming_fingerprint, incoming_kind,
                            incoming_amount_cents, incoming_currency, detected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            record["tenant_id"], record["source"], record["external_id"],
                            batch_id, existing["fingerprint"], existing["kind"],
                            existing["amount_cents"], existing["currency"],
                            record["fingerprint"], record["kind"],
                            record["amount_cents"], record["currency"], now,
                        ),
                    )
                    conflicts += 1

            status = "review_required" if conflicts else "complete"
            self.conn.execute(
                """UPDATE import_batches
                   SET inserted_count = ?, duplicate_count = ?, conflict_count = ?,
                       status = ?, completed_at = ?
                   WHERE batch_id = ?""",
                (inserted, duplicates, conflicts, status, _utc_now(), batch_id),
            )

        summary = self._batch_summary(batch_id)
        summary["replayed"] = False
        return summary

    def list_transactions(self, tenant_id: str, *, kinds=None) -> list[dict]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        tenant_id = tenant_id.strip()
        params = [tenant_id]
        where = "tenant_id = ?"
        if kinds is not None:
            kinds = [str(kind).strip().lower() for kind in kinds]
            if not kinds or any(kind not in VALID_KINDS for kind in kinds):
                raise ValueError("Invalid transaction kind filter")
            where += " AND kind IN ({})".format(",".join("?" for _ in kinds))
            params.extend(kinds)
        rows = self.conn.execute(
            f"""SELECT tenant_id, source, external_id, kind, amount_cents,
                       currency, first_batch_id, first_seen_at, last_seen_at
                FROM transactions WHERE {where}
                ORDER BY source, external_id""",
            params,
        ).fetchall()
        return [
            {
                "tenant_id": row["tenant_id"],
                "source": row["source"],
                "external_id": row["external_id"],
                "kind": row["kind"],
                "amount": _from_cents(row["amount_cents"]),
                "currency": row["currency"],
                "first_batch_id": row["first_batch_id"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        ]

    def list_conflicts(self, tenant_id: str, *, unresolved_only: bool = True) -> list[dict]:
        query = "SELECT * FROM transaction_conflicts WHERE tenant_id = ?"
        params = [tenant_id]
        if unresolved_only:
            query += " AND resolution IS NULL"
        query += " ORDER BY id"
        rows = self.conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["existing_amount"] = _from_cents(item.pop("existing_amount_cents"))
            item["incoming_amount"] = _from_cents(item.pop("incoming_amount_cents"))
            result.append(item)
        return result

    def resolve_conflict(self, conflict_id: int, resolution: str, *, note: str = "") -> dict:
        """Resolve a stored conflict without losing the audit record.

        resolution is 'keep_existing' or 'accept_incoming'. Reconciled records
        cannot be replaced because that could invalidate an already confirmed
        transfer link.
        """
        if resolution not in {"keep_existing", "accept_incoming"}:
            raise ValueError("resolution must be keep_existing or accept_incoming")
        row = self.conn.execute(
            "SELECT * FROM transaction_conflicts WHERE id = ?", (conflict_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Conflict not found")
        if row["resolution"] is not None:
            if row["resolution"] != resolution:
                raise ValueError("Conflict is already resolved differently")
            result = dict(row)
            result["replayed"] = True
            return result

        key = (row["tenant_id"], row["source"], row["external_id"])
        with self.conn:
            if resolution == "accept_incoming":
                linked = self.conn.execute(
                    """SELECT id FROM reconciliation_links
                       WHERE tenant_id = ? AND
                         ((payout_source = ? AND payout_external_id = ?) OR
                          (deposit_source = ? AND deposit_external_id = ?))""",
                    (row["tenant_id"], row["source"], row["external_id"],
                     row["source"], row["external_id"]),
                ).fetchone()
                if linked:
                    raise ValueError("Cannot replace a reconciled transaction")
                current = self.conn.execute(
                    """SELECT fingerprint FROM transactions
                       WHERE tenant_id = ? AND source = ? AND external_id = ?""",
                    key,
                ).fetchone()
                if current is None or current["fingerprint"] != row["existing_fingerprint"]:
                    raise ValueError("Canonical transaction changed; review again")
                self.conn.execute(
                    """UPDATE transactions
                       SET kind = ?, amount_cents = ?, currency = ?, fingerprint = ?,
                           last_seen_at = ?
                       WHERE tenant_id = ? AND source = ? AND external_id = ?""",
                    (
                        row["incoming_kind"], row["incoming_amount_cents"],
                        row["incoming_currency"], row["incoming_fingerprint"],
                        _utc_now(), *key,
                    ),
                )

            self.conn.execute(
                """UPDATE transaction_conflicts
                   SET resolution = ?, resolution_note = ?, resolved_at = ?
                   WHERE id = ?""",
                (resolution, note, _utc_now(), conflict_id),
            )

        result = dict(self.conn.execute(
            "SELECT * FROM transaction_conflicts WHERE id = ?", (conflict_id,)
        ).fetchone())
        result["replayed"] = False
        return result

    def find_reconciliation_candidates(self, tenant_id: str) -> dict:
        """Find exact unmatched payout/deposit pairs without auto-confirming them.

        Only amount/currency groups with exactly one unmatched payout and one
        unmatched bank deposit are returned as candidates. Repeated equal
        amounts are reported as ambiguous and require manual investigation.
        """
        payouts = self.conn.execute(
            """SELECT t.* FROM transactions t
               LEFT JOIN reconciliation_links r
                 ON t.tenant_id = r.tenant_id
                AND t.source = r.payout_source
                AND t.external_id = r.payout_external_id
               WHERE t.tenant_id = ? AND t.kind = 'payout' AND r.id IS NULL""",
            (tenant_id,),
        ).fetchall()
        deposits = self.conn.execute(
            """SELECT t.* FROM transactions t
               LEFT JOIN reconciliation_links r
                 ON t.tenant_id = r.tenant_id
                AND t.source = r.deposit_source
                AND t.external_id = r.deposit_external_id
               WHERE t.tenant_id = ? AND t.kind = 'bank_deposit' AND r.id IS NULL""",
            (tenant_id,),
        ).fetchall()

        payout_groups = defaultdict(list)
        deposit_groups = defaultdict(list)
        for row in payouts:
            payout_groups[(row["amount_cents"], row["currency"])].append(row)
        for row in deposits:
            deposit_groups[(row["amount_cents"], row["currency"])].append(row)

        candidates = []
        ambiguous = []
        for key in sorted(set(payout_groups) & set(deposit_groups)):
            ps = payout_groups[key]
            ds = deposit_groups[key]
            amount_cents, currency = key
            if len(ps) == 1 and len(ds) == 1:
                candidates.append({
                    "payout_source": ps[0]["source"],
                    "payout_external_id": ps[0]["external_id"],
                    "deposit_source": ds[0]["source"],
                    "deposit_external_id": ds[0]["external_id"],
                    "amount": _from_cents(amount_cents),
                    "currency": currency,
                    "status": "suggested_exact_match",
                })
            else:
                ambiguous.append({
                    "amount": _from_cents(amount_cents),
                    "currency": currency,
                    "payout_count": len(ps),
                    "deposit_count": len(ds),
                    "status": "ambiguous_manual_review",
                })
        return {"candidates": candidates, "ambiguous_groups": ambiguous}

    def confirm_reconciliation(
        self,
        tenant_id: str,
        *,
        payout_source: str,
        payout_external_id: str,
        deposit_source: str,
        deposit_external_id: str,
        note: str = "",
    ) -> dict:
        """Explicitly confirm one exact payout-to-bank-deposit relationship."""
        values = [tenant_id, payout_source, payout_external_id, deposit_source, deposit_external_id]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Reconciliation keys must be non-empty strings")
        tenant_id = tenant_id.strip()
        payout_source = payout_source.strip().lower()
        payout_external_id = payout_external_id.strip()
        deposit_source = deposit_source.strip().lower()
        deposit_external_id = deposit_external_id.strip()

        exact = self.conn.execute(
            """SELECT * FROM reconciliation_links
               WHERE tenant_id = ? AND payout_source = ? AND payout_external_id = ?
                 AND deposit_source = ? AND deposit_external_id = ?""",
            (tenant_id, payout_source, payout_external_id,
             deposit_source, deposit_external_id),
        ).fetchone()
        if exact:
            result = dict(exact)
            result["amount"] = _from_cents(result.pop("amount_cents"))
            result["replayed"] = True
            return result

        payout = self.conn.execute(
            """SELECT * FROM transactions
               WHERE tenant_id = ? AND source = ? AND external_id = ?""",
            (tenant_id, payout_source, payout_external_id),
        ).fetchone()
        deposit = self.conn.execute(
            """SELECT * FROM transactions
               WHERE tenant_id = ? AND source = ? AND external_id = ?""",
            (tenant_id, deposit_source, deposit_external_id),
        ).fetchone()
        if payout is None or payout["kind"] != "payout":
            raise ValueError("Payout transaction not found")
        if deposit is None or deposit["kind"] != "bank_deposit":
            raise ValueError("Bank deposit transaction not found")
        if payout["amount_cents"] != deposit["amount_cents"] or payout["currency"] != deposit["currency"]:
            raise ValueError("Payout and bank deposit must have the same amount and currency")

        occupied = self.conn.execute(
            """SELECT id FROM reconciliation_links
               WHERE tenant_id = ? AND
                    ((payout_source = ? AND payout_external_id = ?) OR
                     (deposit_source = ? AND deposit_external_id = ?))""",
            (tenant_id, payout_source, payout_external_id,
             deposit_source, deposit_external_id),
        ).fetchone()
        if occupied:
            raise ValueError("One of these transactions is already reconciled")

        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO reconciliation_links
                   (tenant_id, payout_source, payout_external_id,
                    deposit_source, deposit_external_id, amount_cents,
                    currency, confirmed_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id, payout_source, payout_external_id,
                    deposit_source, deposit_external_id,
                    payout["amount_cents"], payout["currency"], _utc_now(), note,
                ),
            )
        row = dict(self.conn.execute(
            "SELECT * FROM reconciliation_links WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())
        row["amount"] = _from_cents(row.pop("amount_cents"))
        row["replayed"] = False
        return row

    def reconciliation_status(self, tenant_id: str) -> dict:
        payout_count = self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE tenant_id = ? AND kind = 'payout'",
            (tenant_id,),
        ).fetchone()[0]
        deposit_count = self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE tenant_id = ? AND kind = 'bank_deposit'",
            (tenant_id,),
        ).fetchone()[0]
        link_count = self.conn.execute(
            "SELECT COUNT(*) FROM reconciliation_links WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()[0]
        conflict_count = self.conn.execute(
            """SELECT COUNT(*) FROM transaction_conflicts
               WHERE tenant_id = ? AND resolution IS NULL""",
            (tenant_id,),
        ).fetchone()[0]
        return {
            "recorded_payouts": payout_count,
            "recorded_bank_deposits": deposit_count,
            "confirmed_links": link_count,
            "unmatched_payouts": payout_count - link_count,
            "unmatched_bank_deposits": deposit_count - link_count,
            "unresolved_conflicts": conflict_count,
            "recorded_transfers_reconciled": (
                link_count > 0
                and payout_count == link_count
                and deposit_count == link_count
                and conflict_count == 0
            ),
            "note": "This verifies only recorded payout/deposit links; it does not prove source completeness or bank balance accuracy.",
        }
