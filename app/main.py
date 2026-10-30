from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .exporter import csv_report, html_report, json_report
from .models import QueryInput
from .provider import Provider
from .service import Engine
from .settings import ROOT, Settings
from .store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings=settings or Settings.load()
    store=Store(settings.data_dir)
    engine=Engine(settings,store,Provider(settings))
    running: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(app):
        store.interrupt_unfinished()
        yield
        for task in list(running):
            task.cancel()
        if running:
            await asyncio.gather(*running,return_exceptions=True)

    app=FastAPI(title='采证 · 采购成交信息工作台',version='1.0.0',lifespan=lifespan)
    app.state.store=store

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.url.path.startswith('/api/') and request.url.path not in ('/api/health','/api/config'):
            if settings.access_token and not secrets.compare_digest(request.headers.get('x-app-token',''),settings.access_token):
                return JSONResponse({'detail':'请填写工作台访问口令'},status_code=401)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.get('/api/health')
    async def health():
        return {'ok':True,'version':'1.0.0'}

    @app.get('/api/config')
    async def config():
        return {'live_available':bool(settings.key),'auth_required':bool(settings.access_token),
                'demo_captured_on':'2026-10-30','version':'1.0.0'}

    @app.post('/api/tasks',status_code=202)
    async def submit(req: QueryInput):
        if running:
            raise HTTPException(409,'已有查询任务正在执行，请等待完成。')
        if req.mode=='live' and not settings.key:
            raise HTTPException(400,'服务端尚未配置元宝搜索密钥，可先使用示例回放。')
        if req.mode=='demo' and (req.keyword!='智慧黑板' or req.region!='江西' or req.site):
            raise HTTPException(422,'示例回放固定为：智慧黑板、江西、全部来源。可切换实时查询自定义条件。')
        task=engine.new(req)
        future=asyncio.create_task(engine.run(task))
        running.add(future);future.add_done_callback(running.discard)
        return task

    @app.get('/api/tasks')
    async def history():
        return [{'id':t['id'],'created_at':t['created_at'],'input':t['input'],
                 'status':t['status'],'stats':t['stats']} for t in store.list()]

    def get_task(task_id):
        task=store.get(task_id)
        if task is None:
            raise HTTPException(404,'查询任务不存在')
        return task

    @app.get('/api/tasks/{task_id}')
    async def detail(task_id: str):
        return get_task(task_id)

    @app.get('/api/tasks/{task_id}/export')
    async def export(task_id: str, format: str='html'):
        task=get_task(task_id)
        if task['status'] in ('queued','running'):
            raise HTTPException(409,'任务尚未完成，请稍后导出。')
        name=f'procurement-{task_id}'
        if format=='html':
            return Response(html_report(task),media_type='text/html',headers={'Content-Disposition':f'attachment; filename="{name}.html"'})
        if format=='csv':
            return Response(csv_report(task),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}.csv"'})
        if format=='json':
            return Response(json_report(task),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{name}.json"'})
        raise HTTPException(400,'支持的导出格式为 html、csv、json')

    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

    @app.get('/')
    async def index():
        return FileResponse(ROOT/'static/index.html')

    return app


app=create_app()
