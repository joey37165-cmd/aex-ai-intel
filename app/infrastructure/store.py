from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.models import AnalysisResult, ContentItem
from app.domain.deduplication import are_semantic_duplicates
from app.domain.status import DeliveryStatus, ItemStatus, ReportStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_name TEXT NOT NULL,
                category TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, summary TEXT NOT NULL,
                published_at TEXT, image_url TEXT, discovered_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                item_id TEXT PRIMARY KEY REFERENCES items(item_id), decision TEXT NOT NULL,
                priority TEXT NOT NULL, category TEXT NOT NULL, summary TEXT NOT NULL,
                why_it_matters TEXT NOT NULL, suggested_action TEXT NOT NULL, confidence REAL NOT NULL,
                display_title TEXT NOT NULL DEFAULT '',
                event_json TEXT NOT NULL DEFAULT '{}',
                raw_json TEXT NOT NULL, model_name TEXT NOT NULL DEFAULT 'unknown',
                prompt_version TEXT NOT NULL DEFAULT 'unknown', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                item_id TEXT PRIMARY KEY REFERENCES items(item_id), status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, telegram_message_id TEXT, last_error TEXT,
                next_attempt_at TEXT, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
                discovered_count INTEGER NOT NULL DEFAULT 0, analyzed_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS source_state (
                source_id TEXT PRIMARY KEY, last_attempt_at TEXT, last_success_at TEXT,
                next_poll_at TEXT, last_item_count INTEGER NOT NULL DEFAULT 0, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY, report_type TEXT NOT NULL,
                period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT, prompt_version TEXT,
                telegram_message_id TEXT, last_error TEXT, next_attempt_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS message_templates (
                template_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                draft_content TEXT NOT NULL, draft_revision INTEGER NOT NULL DEFAULT 1,
                published_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS message_template_versions (
                template_id TEXT NOT NULL REFERENCES message_templates(template_id),
                version INTEGER NOT NULL, content TEXT NOT NULL,
                published_at TEXT NOT NULL, created_by TEXT NOT NULL,
                PRIMARY KEY (template_id, version)
            );
            """
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(analyses)")}
        for column in ("model_name", "prompt_version", "display_title", "event_json"):
            if column not in columns:
                if column == "display_title":
                    default = "''"
                elif column == "event_json":
                    default = "'{}'"
                else:
                    default = "'unknown'"
                self.connection.execute(f"ALTER TABLE analyses ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")
        item_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(items)")}
        if "image_url" not in item_columns:
            self.connection.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
        self.connection.commit()

    def initialize_template(self, template_id: str, name: str, description: str, content: str) -> None:
        now = utc_now()
        self.connection.execute(
            """INSERT OR IGNORE INTO message_templates
            (template_id, name, description, draft_content, draft_revision,
             published_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)""",
            (template_id, name, description, content, now, now),
        )
        self.connection.execute(
            """INSERT OR IGNORE INTO message_template_versions
            (template_id, version, content, published_at, created_by)
            VALUES (?, 1, ?, ?, 'system')""",
            (template_id, content, now),
        )
        self.connection.commit()

    def template_summaries(self) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            """SELECT template_id, name, description, draft_revision,
            published_version, updated_at,
            CASE WHEN draft_content = (
                SELECT content FROM message_template_versions v
                WHERE v.template_id=message_templates.template_id
                  AND v.version=message_templates.published_version
            ) THEN 'published' ELSE 'draft' END AS status
            FROM message_templates ORDER BY template_id DESC"""
        ))

    def template_detail(self, template_id: str) -> dict | None:
        row = self.connection.execute(
            """SELECT template_id, name, description, draft_content, draft_revision,
            published_version, updated_at,
            CASE WHEN draft_content = (
                SELECT content FROM message_template_versions v
                WHERE v.template_id=message_templates.template_id
                  AND v.version=message_templates.published_version
            ) THEN 'published' ELSE 'draft' END AS status
            FROM message_templates WHERE template_id=?""",
            (template_id,),
        ).fetchone()
        if row is None:
            return None
        versions = self.connection.execute(
            """SELECT version, content, published_at, created_by
            FROM message_template_versions WHERE template_id=? ORDER BY version DESC""",
            (template_id,),
        ).fetchall()
        result = dict(row)
        result["versions"] = [dict(version) for version in versions]
        return result

    def save_template_draft(self, template_id: str, content: str, expected_revision: int) -> dict | None:
        cursor = self.connection.execute(
            """UPDATE message_templates SET draft_content=?, draft_revision=draft_revision+1,
            updated_at=? WHERE template_id=? AND draft_revision=?""",
            (content, utc_now(), template_id, expected_revision),
        )
        self.connection.commit()
        return self.template_detail(template_id) if cursor.rowcount == 1 else None

    def publish_template(self, template_id: str, expected_revision: int, created_by: str) -> dict | None:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                """SELECT t.draft_content, t.draft_revision, t.published_version,
                v.content AS published_content
                FROM message_templates t
                JOIN message_template_versions v
                  ON v.template_id=t.template_id AND v.version=t.published_version
                WHERE t.template_id=?""",
                (template_id,),
            ).fetchone()
            if (
                row is None
                or int(row["draft_revision"]) != expected_revision
                or row["draft_content"] == row["published_content"]
            ):
                self.connection.rollback()
                return None
            next_version = int(row["published_version"]) + 1
            now = utc_now()
            self.connection.execute(
                """INSERT INTO message_template_versions
                (template_id, version, content, published_at, created_by)
                VALUES (?, ?, ?, ?, ?)""",
                (template_id, next_version, row["draft_content"], now, created_by[:100]),
            )
            self.connection.execute(
                """UPDATE message_templates SET published_version=?, updated_at=?
                WHERE template_id=?""",
                (next_version, now, template_id),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return self.template_detail(template_id)

    def restore_template_version(self, template_id: str, version: int, expected_revision: int) -> dict | None:
        row = self.connection.execute(
            """SELECT content FROM message_template_versions
            WHERE template_id=? AND version=?""",
            (template_id, version),
        ).fetchone()
        if row is None:
            return None
        return self.save_template_draft(template_id, str(row["content"]), expected_revision)

    def template_version_exists(self, template_id: str, version: int) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM message_template_versions WHERE template_id=? AND version=?",
            (template_id, version),
        ).fetchone()
        return row is not None

    def get_published_template(self, template_id: str) -> str | None:
        row = self.connection.execute(
            """SELECT v.content FROM message_templates t
            JOIN message_template_versions v
              ON v.template_id=t.template_id AND v.version=t.published_version
            WHERE t.template_id=?""",
            (template_id,),
        ).fetchone()
        return str(row["content"]) if row else None

    def close(self) -> None:
        self.connection.close()

    def item_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()
        return int(row["count"])

    def save_item(self, item: ContentItem, status: str = ItemStatus.DISCOVERED) -> bool:
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO items
            (item_id, source_id, source_name, category, title, url, summary, published_at,
             image_url, discovered_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.item_id, item.source_id, item.source_name, item.category, item.title, item.url,
             item.summary, item.published_at.isoformat() if item.published_at else None,
             item.image_url,
             item.discovered_at.isoformat(), status, utc_now()),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def has_analysis(self, item_id: str) -> bool:
        row = self.connection.execute("SELECT 1 FROM analyses WHERE item_id=?", (item_id,)).fetchone()
        return row is not None

    def item_status(self, item_id: str) -> str | None:
        row = self.connection.execute("SELECT status FROM items WHERE item_id=?", (item_id,)).fetchone()
        return str(row["status"]) if row else None

    def source_is_due(self, source_id: str) -> bool:
        row = self.connection.execute(
            "SELECT next_poll_at FROM source_state WHERE source_id=?", (source_id,)
        ).fetchone()
        return row is None or row["next_poll_at"] is None or row["next_poll_at"] <= utc_now()

    def source_state_exists(self, source_id: str) -> bool:
        row = self.connection.execute("SELECT 1 FROM source_state WHERE source_id=?", (source_id,)).fetchone()
        return row is not None

    def source_has_never_succeeded(self, source_id: str) -> bool:
        row = self.connection.execute(
            "SELECT last_success_at FROM source_state WHERE source_id=?", (source_id,)
        ).fetchone()
        return row is not None and row["last_success_at"] is None

    def mark_source_result(self, source_id: str, interval_minutes: int, item_count: int, error: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        retry_minutes = min(5, interval_minutes) if error else interval_minutes
        next_poll = (now + timedelta(minutes=max(1, retry_minutes))).isoformat()
        self.connection.execute(
            """INSERT INTO source_state
            (source_id, last_attempt_at, last_success_at, next_poll_at, last_item_count, last_error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              last_attempt_at=excluded.last_attempt_at,
              last_success_at=CASE WHEN excluded.last_error IS NULL THEN excluded.last_success_at ELSE source_state.last_success_at END,
              next_poll_at=excluded.next_poll_at, last_item_count=excluded.last_item_count,
              last_error=excluded.last_error""",
            (source_id, now.isoformat(), None if error else now.isoformat(), next_poll, item_count, error[:500] if error else None),
        )
        self.connection.commit()

    def report_candidates(self, period_start: str, period_end: str, limit: int = 40) -> list[sqlite3.Row]:
        limit = max(1, min(limit, 100))
        return list(self.connection.execute(
            """SELECT i.item_id, i.source_name, i.title, i.url,
            a.category, a.priority, a.summary, a.why_it_matters,
            COALESCE(i.published_at, i.discovered_at) AS occurred_at
            FROM analyses a JOIN items i ON i.item_id=a.item_id
            WHERE a.decision=? AND a.priority IN ('S', 'A')
              AND julianday(COALESCE(i.published_at, i.discovered_at)) >= julianday(?)
              AND julianday(COALESCE(i.published_at, i.discovered_at)) < julianday(?)
            ORDER BY CASE a.priority WHEN 'S' THEN 0 ELSE 1 END,
                     julianday(COALESCE(i.published_at, i.discovered_at)) DESC
            LIMIT ?""",
            (ItemStatus.NOTIFY, period_start, period_end, limit),
        ))

    def ensure_report(self, report_id: str, report_type: str, period_start: str, period_end: str) -> sqlite3.Row:
        now = utc_now()
        self.connection.execute(
            """INSERT OR IGNORE INTO reports
            (report_id, report_type, period_start, period_end, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (report_id, report_type, period_start, period_end, now, now),
        )
        self.connection.commit()
        return self.report(report_id)

    def report(self, report_id: str) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
        if row is None:
            raise KeyError(f"未知报告: {report_id}")
        return row

    def retryable_reports(self) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            """SELECT * FROM reports
            WHERE status IN (?, ?)
               OR (status=? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
            ORDER BY period_end ASC""",
            (ReportStatus.PENDING, ReportStatus.READY, ReportStatus.RETRY, utc_now()),
        ))

    def save_report_payload(self, report_id: str, payload: dict, prompt_version: str) -> None:
        self.connection.execute(
            """UPDATE reports SET status=?, payload_json=?, prompt_version=?,
            last_error=NULL, next_attempt_at=NULL, updated_at=? WHERE report_id=?""",
            (ReportStatus.READY, json.dumps(payload, ensure_ascii=False), prompt_version, utc_now(), report_id),
        )
        self.connection.commit()

    def mark_report_sent(self, report_id: str, message_id: str) -> None:
        self.connection.execute(
            """UPDATE reports SET status=?, telegram_message_id=?, last_error=NULL,
            next_attempt_at=NULL, updated_at=? WHERE report_id=?""",
            (ReportStatus.SENT, message_id, utc_now(), report_id),
        )
        self.connection.commit()

    def mark_report_retry(self, report_id: str, error: str, attempts: int) -> None:
        delay = min(3600, 2 ** min(attempts, 10))
        next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.connection.execute(
            """UPDATE reports SET status=?, attempts=?, last_error=?,
            next_attempt_at=?, updated_at=? WHERE report_id=?""",
            (ReportStatus.RETRY, attempts, error[:500], next_attempt, utc_now(), report_id),
        )
        self.connection.commit()

    def save_analysis(self, item_id: str, result: AnalysisResult, model_name: str = "unknown", prompt_version: str = "unknown") -> None:
        self.connection.execute(
            """INSERT INTO analyses
            (item_id, decision, priority, category, summary, why_it_matters, suggested_action,
             confidence, display_title, event_json, raw_json, model_name, prompt_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET decision=excluded.decision, priority=excluded.priority,
            category=excluded.category, summary=excluded.summary, why_it_matters=excluded.why_it_matters,
            suggested_action=excluded.suggested_action, confidence=excluded.confidence,
            display_title=excluded.display_title,
            event_json=excluded.event_json, raw_json=excluded.raw_json, model_name=excluded.model_name,
            prompt_version=excluded.prompt_version, created_at=excluded.created_at""",
            (item_id, result.decision, result.priority, result.category, result.summary,
             result.why_it_matters, result.suggested_action, result.confidence, result.display_title,
             json.dumps(asdict(result.event), ensure_ascii=False),
             json.dumps(result.raw, ensure_ascii=False), model_name, prompt_version, utc_now()),
        )
        self.connection.execute("UPDATE items SET status=? WHERE item_id=?", (result.decision, item_id))
        self.connection.commit()

    def queue_delivery(self, item_id: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO deliveries (item_id, updated_at) VALUES (?, ?)", (item_id, utc_now())
        )
        self.connection.commit()

    def find_recent_notification_duplicate(
        self, item: ContentItem, lookback_hours: int = 72
    ) -> sqlite3.Row | None:
        occurred_at = item.published_at or item.discovered_at
        start = (occurred_at - timedelta(hours=lookback_hours)).isoformat()
        end = (occurred_at + timedelta(hours=lookback_hours)).isoformat()
        rows = self.connection.execute(
            """SELECT i.item_id, i.source_name, i.title, i.summary,
            a.display_title, a.summary AS analysis_summary
            FROM analyses a JOIN items i ON i.item_id=a.item_id
            WHERE a.decision=?
              AND julianday(COALESCE(i.published_at, i.discovered_at)) >= julianday(?)
              AND julianday(COALESCE(i.published_at, i.discovered_at)) <= julianday(?)
              AND i.item_id != ?
            ORDER BY COALESCE(i.published_at, i.discovered_at) ASC""",
            (ItemStatus.NOTIFY, start, end, item.item_id),
        ).fetchall()
        for row in rows:
            if are_semantic_duplicates(
                item.title,
                item.summary,
                row["display_title"] or row["title"],
                row["analysis_summary"] or row["summary"],
            ):
                return row
        return None

    def pending_deliveries(self) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            """SELECT d.*, i.source_name, i.category, i.title, i.url, i.summary, i.published_at, i.image_url,
            a.category AS analysis_category, a.summary AS analysis_summary, a.priority,
            a.why_it_matters, a.suggested_action, a.display_title FROM deliveries d
            JOIN items i ON i.item_id=d.item_id JOIN analyses a ON a.item_id=d.item_id
            WHERE d.status=? OR (d.status=? AND
            (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)) ORDER BY i.published_at ASC""",
            (DeliveryStatus.PENDING, DeliveryStatus.RETRY, utc_now())
        ))

    def review_items(self, limit: int = 50) -> list[sqlite3.Row]:
        limit = max(1, min(limit, 200))
        return list(self.connection.execute(
            """SELECT i.item_id, i.source_name, i.title, i.url, i.published_at,
            a.priority, a.category, a.summary, a.why_it_matters, a.suggested_action,
            a.confidence, a.model_name, a.prompt_version, a.display_title, a.created_at
            FROM analyses a JOIN items i ON i.item_id=a.item_id
            WHERE a.decision='review'
            ORDER BY COALESCE(i.published_at, i.discovered_at) DESC LIMIT ?""", (limit,)
        ))

    def mark_sent(self, item_id: str, message_id: str) -> None:
        self.connection.execute(
            "UPDATE deliveries SET status=?, telegram_message_id=?, updated_at=? WHERE item_id=?",
            (DeliveryStatus.SENT, message_id, utc_now(), item_id),
        )
        self.connection.execute("UPDATE items SET status=? WHERE item_id=?", (ItemStatus.SENT, item_id))
        self.connection.commit()

    def mark_retry(self, item_id: str, error: str, attempts: int) -> None:
        delay = min(3600, 2 ** min(attempts, 10))
        next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.connection.execute(
            "UPDATE deliveries SET status=?, attempts=?, last_error=?, next_attempt_at=?, updated_at=? WHERE item_id=?",
            (DeliveryStatus.RETRY, attempts, error[:500], next_attempt, utc_now(), item_id),
        )
        self.connection.commit()

    def begin_job(self) -> int:
        cursor = self.connection.execute("INSERT INTO job_runs (started_at) VALUES (?)", (utc_now(),))
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_job(self, job_id: int, discovered: int, analyzed: int, sent: int, errors: int, last_error: str | None) -> None:
        self.connection.execute(
            "UPDATE job_runs SET finished_at=?, discovered_count=?, analyzed_count=?, sent_count=?, error_count=?, last_error=? WHERE id=?",
            (utc_now(), discovered, analyzed, sent, errors, last_error, job_id),
        )
        self.connection.commit()

    def status_summary(self) -> dict:
        def count(table: str) -> int:
            return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        delivery_rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM deliveries GROUP BY status"
        ).fetchall()
        decision_rows = self.connection.execute(
            "SELECT decision, COUNT(*) AS count FROM analyses GROUP BY decision"
        ).fetchall()
        priority_rows = self.connection.execute(
            "SELECT priority, COUNT(*) AS count FROM analyses GROUP BY priority"
        ).fetchall()
        report_rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM reports GROUP BY status"
        ).fetchall()
        latest_report = self.connection.execute(
            """SELECT report_id, report_type, period_start, period_end, status, attempts,
            telegram_message_id, last_error, prompt_version, updated_at
            FROM reports ORDER BY period_end DESC LIMIT 1"""
        ).fetchone()
        latest = self.connection.execute(
            """SELECT started_at, finished_at, discovered_count, analyzed_count,
            sent_count, error_count, last_error FROM job_runs ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        source_rows = self.connection.execute(
            """SELECT source_id, last_attempt_at, last_success_at, next_poll_at,
            last_item_count, last_error FROM source_state ORDER BY source_id"""
        ).fetchall()
        return {
            "items": count("items"),
            "analyses": count("analyses"),
            "analysis_decisions": {row["decision"]: row["count"] for row in decision_rows},
            "analysis_priorities": {row["priority"]: row["count"] for row in priority_rows},
            "deliveries": {row["status"]: row["count"] for row in delivery_rows},
            "reports": {row["status"]: row["count"] for row in report_rows},
            "latest_report": dict(latest_report) if latest_report else None,
            "latest_job": dict(latest) if latest else None,
            "sources": [dict(row) for row in source_rows],
        }
