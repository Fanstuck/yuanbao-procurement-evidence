from __future__ import annotations

import json
from pathlib import Path
import sqlite3


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'workbench.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT NOT NULL)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def save(self, task: dict):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?)',
                       (task['id'], task['created_at'], json.dumps(task, ensure_ascii=False)))

    def get(self, task_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM tasks WHERE id=?', (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit: int = 50):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM tasks ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def interrupt_unfinished(self):
        for task in self.list(10000):
            if task['status'] in ('queued', 'running'):
                task.update(status='interrupted', stage='任务中断', error='服务重启中断了任务，请重新提交。')
                self.save(task)
