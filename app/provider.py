from __future__ import annotations

from datetime import datetime
import json
import ssl
from time import perf_counter
from urllib.parse import urljoin, urlsplit

import httpx

from .parser import CN
from .settings import ROOT, Settings

HOSTS = {'ccgp.gov.cn', 'jxsggzy.cn', 'ggzy.jiangxi.gov.cn', 'zfcg.jxf.gov.cn', 'ggzyjy.shandong.gov.cn'}


class ServiceError(RuntimeError):
    pass


def validate_source_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        if not any(host == root or host.endswith('.'+root) for root in HOSTS):
            raise ValueError()
    except ValueError as error:
        raise ServiceError('该网址不在受支持的 HTTPS 官方来源范围内') from error
    return url


class Provider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.demo = json.loads((ROOT/'fixtures/demo.json').read_text(encoding='utf-8'))

    async def search(self, payload: dict, mode: str) -> tuple[list[dict], dict]:
        start = perf_counter()
        if mode == 'demo':
            run = self.demo['search']
            return run['pages'], {'payload':run['payload'], 'requested_payload':payload, 'request_id':run['request_id'],
                'version':'standard（历史回放）', 'elapsed_seconds':0,
                'queried_at':datetime.now(CN).isoformat(), 'replayed':True,
                'snapshot_date':self.demo['captured_on']}
        if not self.settings.key:
            raise ServiceError('服务端未配置元宝搜索密钥，可先切换示例回放。')
        try:
            async with httpx.AsyncClient(timeout=30, trust_env=self.settings.trust_env) as client:
                response = await client.post('https://api.wsa.cloud.tencent.com/SearchPro',
                    json=payload, headers={'Authorization':'Bearer '+self.settings.key})
                response.raise_for_status()
                result = response.json().get('Response', {})
        except (httpx.HTTPError, ssl.SSLError, ValueError) as error:
            raise ServiceError('元宝搜索连接或响应异常：'+type(error).__name__) from error
        if result.get('Error'):
            raise ServiceError('元宝搜索返回错误：'+str(result['Error'].get('Code', 'Unknown')))
        if not isinstance(result.get('Pages'), list):
            raise ServiceError('元宝搜索响应缺少页面列表')
        pages = []
        for raw in result['Pages'][:20]:
            try:
                p = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(p, dict) and p.get('url') and p.get('title') and urlsplit(str(p['url'])).scheme == 'https':
                    pages.append({k:p.get(k, '') for k in ('title','url','date','site')})
            except (ValueError, TypeError):
                continue
        return pages, {'payload':payload, 'request_id':result.get('RequestId'),
            'version':result.get('Version'), 'elapsed_seconds':round(perf_counter()-start,3),
            'queried_at':datetime.now(CN).isoformat(), 'replayed':False}

    async def fetch(self, url: str, mode: str) -> tuple[bytes, str]:
        validate_source_url(url)
        if mode == 'demo':
            text = self.demo['notices'].get(url)
            if text is None:
                raise ServiceError('固定回放样本未收录该正文，保持待复核')
            from html import escape
            return ('<html><meta charset="utf-8"><body><pre>'+escape(text)+'</pre></body></html>').encode(), url
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False,
                    trust_env=self.settings.trust_env, headers={'User-Agent':'ProcurementEvidence/1.0'}) as client:
                current = url
                for _ in range(4):
                    validate_source_url(current)
                    async with client.stream('GET', current) as response:
                        if response.status_code in (301,302,303,307,308):
                            current = urljoin(current, response.headers.get('location', ''))
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get('content-type','').lower()
                        if content_type and not any(t in content_type for t in ('text/', 'application/xhtml')):
                            raise ServiceError('正文为附件或非文本格式，本版保留待复核')
                        chunks=[];size=0
                        async for part in response.aiter_bytes():
                            size += len(part)
                            if size > 2_000_000:
                                raise ServiceError('原文超过读取上限，本版保留待复核')
                            chunks.append(part)
                        return b''.join(chunks), current
                raise ServiceError('原站重定向次数过多')
        except (httpx.HTTPError, ssl.SSLError) as error:
            raise ServiceError('原站访问失败：'+type(error).__name__) from error
