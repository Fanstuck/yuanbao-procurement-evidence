# 工作台接口

如设置 `APP_ACCESS_TOKEN`，除健康检查和配置接口外需携带 `X-App-Token`。实时密钥只配置在服务端。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查与版本 |
| GET | `/api/config` | 实时查询是否可用、是否要求访问口令 |
| POST | `/api/tasks` | 创建查询，返回 202 与任务 ID |
| GET | `/api/tasks` | 最近五十个历史任务 |
| GET | `/api/tasks/{id}` | 进度、日志、结果、检索追踪 |
| GET | `/api/tasks/{id}/export?format=html` | 导出 HTML；也支持 csv、json |

请求示例：

```json
{
  "keyword": "智慧黑板",
  "region": "江西",
  "freshness": "y2",
  "site": "",
  "target": 3,
  "mode": "live",
  "expand_search": true
}
```

`mode` 为 live 或 demo；freshness 支持空值、y1、y2、y3、m6；site 支持全部来源、ccgp.gov.cn、jxsggzy.cn；目标一至十条。

示例回放固定名称、地区和来源，不能借回放声称执行了任意查询。正在运行的任务未结束时再提交，会返回 409。未配置实时密钥时 live 返回 400。不存在的任务返回 404；无效参数返回 422。

返回数据中的 `requests` 是脱敏检索元数据，不包含认证头。回放的请求标识来自历史样本，并明确标记 `replayed=true`，不能算成本次真实调用。
