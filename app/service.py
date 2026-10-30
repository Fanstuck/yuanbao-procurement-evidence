from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import re
from time import perf_counter
from uuid import uuid4

from .models import QueryInput
from .parser import CN, parse_notice, plain_text, title_kind
from .provider import Provider, ServiceError
from .settings import Settings
from .store import Store


def now():
    return datetime.now(CN).isoformat(timespec='seconds')


def deduplicate(records: list[dict]):
    groups = {}
    for record in records:
        if record.get('project_id') and record['status'] == 'verified':
            key = re.sub(r'\s+', '', record['project_id']).upper()
            groups.setdefault(key, []).append(record)
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({r['amount_yuan'] for r in group}) > 1:
            for r in group:
                r.update(status='pending', reason='同项目编号存在不同金额，需确认包件或更正关系')
        else:
            for r in group[1:]:
                r.update(status='duplicate', duplicate_of=group[0]['id'],
                         reason='与另一来源的项目编号及总额相同，本次不重复计入报告')


class Engine:
    def __init__(self, settings: Settings, store: Store, provider: Provider):
        self.settings, self.store, self.provider = settings, store, provider
        self.lock = asyncio.Lock()

    def new(self, req: QueryInput) -> dict:
        task = dict(id=uuid4().hex[:16], created_at=now(), updated_at=now(),
            input=req.model_dump(), status='queued', stage='等待执行', progress=0,
            records=[], requests=[], logs=[], error=None, elapsed_seconds=0,
            stats={'candidates':0,'verified':0,'pending':0,'excluded':0,'duplicate':0})
        self.store.save(task)
        return task

    def update(self, task: dict, stage: str, progress: int, message: str = ''):
        task.update(stage=stage, progress=progress, updated_at=now())
        if message:
            task['logs'].append({'time':now(), 'message':message})
        self.store.save(task)

    async def run(self, task: dict):
        start = perf_counter()
        async with self.lock:
            task['status'] = 'running'
            req = QueryInput(**task['input'])
            try:
                self.update(task, '联网检索' if req.mode=='live' else '读取历史回放', 8,
                    '实时查询使用元宝搜索；示例回放不发起外部请求。')
                payload={'Query':' '.join(x for x in (req.region, req.keyword, '中标 成交公告') if x)}
                if req.freshness:
                    payload['Freshness'] = req.freshness
                if req.site:
                    payload['Site'] = req.site
                pages, meta = await self.provider.search(payload, req.mode)
                task['requests'].append(meta)
                await self.process_pages(task, pages, req)
                verified=sum(r['status']=='verified' for r in task['records'])
                if verified < req.target and req.site and req.expand_search and req.mode=='live':
                    self.update(task, '扩展来源', 72, '有效记录不足，按勾选设置扩大至其他官方来源；时间条件保持。')
                    wider = {k:v for k,v in payload.items() if k != 'Site'}
                    extra, extra_meta = await self.provider.search(wider, req.mode)
                    task['requests'].append(extra_meta)
                    await self.process_pages(task, extra, req)
                deduplicate(task['records'])
                stats={'candidates':len(task['records'])}
                stats.update({s:sum(r['status']==s for r in task['records']) for s in ('verified','pending','excluded','duplicate')})
                task.update(stats=stats, status='completed' if stats['verified']>=req.target else 'partial',
                            elapsed_seconds=round(perf_counter()-start,3))
                message=f"核对通过 {stats['verified']} 条，待复核 {stats['pending']} 条。"
                if stats['verified'] < req.target:
                    message += '未达到目标数量，报告如实标记不足，不补造记录。'
                self.update(task, '任务完成' if task['status']=='completed' else '结果不足', 100, message)
            except asyncio.CancelledError:
                task.update(status='interrupted', error='任务随服务关闭而中断')
                self.update(task, '任务中断', task['progress'])
                raise
            except Exception as error:
                # Error messages are constructed locally; raw HTTP objects/headers are never persisted.
                task.update(status='failed', error=str(error) if isinstance(error, ServiceError) else '处理异常：'+type(error).__name__,
                            elapsed_seconds=round(perf_counter()-start,3))
                self.update(task, '任务失败', 100, task['error'])

    async def process_pages(self, task: dict, pages: list[dict], req: QueryInput):
        known={r['url'] for r in task['records']}
        fresh=[]
        for p in pages:
            if p['url'] not in known:
                known.add(p['url']); fresh.append(p)
        self.update(task, '整理候选', 25, f'新增 {len(fresh)} 条候选，将读取原文并检查金额。')
        sem=asyncio.Semaphore(3)
        initial=len(task['records'])
        async def check(p: dict, index: int):
            async with sem:
                record=dict(id=uuid4().hex[:12], title=p['title'], url=p['url'],
                    search_date=p.get('date',''), fetched_at='', status='pending',
                    reason='', evidence=[], amount_yuan=None, summary_yuan=None,
                    project_id='', published_date='', amount_kind='项目成交总额',
                    comparable_unit_price=False, snapshot_sha256='', mode=req.mode)
                try:
                    kind=title_kind(p['title'])
                    if kind in ('unsuccessful','related'):
                        record.update(parse_notice('', p['title'], req.freshness))
                    else:
                        content, final_url = await self.provider.fetch(p['url'], req.mode)
                        record.update(final_url=final_url, fetched_at=now(),
                                      snapshot_sha256=hashlib.sha256(content).hexdigest())
                        text = plain_text(content)
                        record.update(parse_notice(text,p['title'],'' if req.mode=='demo' else req.freshness))
                        if record['status']=='verified' and req.keyword not in text and req.keyword not in p['title']:
                            record.update(status='pending', reason='关键词未在标题或正文中直接命中，需要核查相关性')
                        folder=self.settings.data_dir/'snapshots'/task['id']
                        folder.mkdir(parents=True,exist_ok=True)
                        (folder/(record['id']+'.html')).write_bytes(content)
                except ServiceError as error:
                    record['reason']=str(error)
                task['records'].append(record)
                done=len(task['records'])-initial
                self.update(task, '原文核对', min(90,30+int(55*done/max(len(fresh),1))),
                            f"{done}/{len(fresh)}：{record['title'][:40]} · {record['reason']}")
        await asyncio.gather(*(check(p,i) for i,p in enumerate(fresh)))
