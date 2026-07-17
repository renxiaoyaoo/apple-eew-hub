# Apple 设备地震预警系统

一个可部署在任意 Docker 主机上的私有地震预警中枢，自带可选的自建 Bark Server，也支持 ntfy 和 Webhook。它可以为你的 Apple 设备提供地震预警提醒，并为每台设备单独设置位置和推送条件。家用服务器、迷你主机、NAS、树莓派、云服务器都可以运行。

## 当前 MVP

- Wolfx WebSocket 监听骨架，支持 `cenc_eew`、`sc_eew`、`cq_eew`、`fj_eew`、`jma_eew`、`all_eew`
- EMSC/SeismicPortal WebSocket 全球特大地震预警，默认 `M7.5+`
- 自建 Bark Server：Docker Compose 默认一起启动，可直接给 Bark App 使用
- Bark / ntfy / Webhook 多通道推送；Bark 是推荐方式，但不是必需
- 多设备管理：城市、经纬度、震级、距离、烈度阈值
- SQLite 日志：事件、判断、推送结果
- 红 / 黄 / 蓝分级预警详情页和地图
- 测试推送
- 模拟地震演练
- Docker Compose 一键部署
- 配置备份、GitHub Actions 和本地 pre-commit 隐私检查

## 部署

最快方式见 [QUICKSTART.md](./QUICKSTART.md)。

```bash
cp example.env .env
docker compose up -d --build
```

不复制 `.env` 也可以启动；复制后更方便填写 Wolfx 地址、Bark 服务地址和公网访问地址。默认 Compose 会同时启动 EEW Hub 和 Bark Server。

打开：

- 管理页：`http://服务器IP:18761/`
- Bark Server：`http://服务器IP:18762/`

把 `服务器IP` 换成你的服务器、NAS、树莓派或其他 Docker 主机 IP。

`WOLFX_WS_URL` 默认留空即可。系统会按 `WOLFX_WS_BASE` 和 `WOLFX_SOURCES` 自动拼接 Wolfx WebSocket。全球特大地震源默认使用 EMSC WebSocket：`wss://www.seismicportal.eu/standing_order/websocket`。

## 线上访问安全

如果通过 Cloudflare Tunnel、frp 或反向代理暴露管理页，必须设置管理 Token：

```env
EEW_AUTH_TOKEN=换成一段足够长的随机字符串
PUBLIC_BASE_URL=https://你的访问域名
```

设置后，管理 API 需要 Bearer Token。网页会提示填写“管理 Token”，Token 只保存在浏览器 `localStorage`。`/api/health` 和 `/api/status` 保持可用于面板和健康探测。

健康检查：

```bash
curl http://服务器IP:18761/api/health
docker compose ps
```

## 自建 Bark Server

Docker Compose 默认会启动 `bark-server`，你可以把 Bark App 的服务器地址切换到自己的域名或局域网地址，再把设备 Key 填进 EEW Hub。

推荐使用 Bark，因为 iPhone 上的提醒效果最好。Bark 推送参数使用：

- `sound=alarm`
- 红 / 黄等级使用 `level=critical`
- 蓝等级使用 `level=timeSensitive`
- `group=earthquake`
- `isArchive=1`
- `url` 指向这次地震的独立详情页 `/event/{event_id}`

iOS 是否能达到 critical 级别取决于 Bark 客户端、系统权限和应用能力。MVP 使用高优先级、特殊铃声和网页卡片补充。

## Bark 是否必需

不必需。Bark 是推荐的 Apple 设备通知通道，但系统可以不使用 Bark：

- 使用 `ntfy`：填写 topic URL。
- 使用 `webhook`：对接 Home Assistant、Node-RED 或你自己的自动化。
- 不配置推送设备：仍可使用实时地震记录、预警历史、演练、地图和独立预警页。

## ntfy / Webhook

设备的推送方式可以选择：

- `bark`：填写 Bark Key
- `ntfy`：填写 topic URL，例如 `https://ntfy.sh/your-topic`
- `webhook`：填写接收 JSON 的 HTTP URL，可对接 Home Assistant、Node-RED 或自建自动化

Webhook payload 包含 `title`、`body`、`event` 和 `decision`。

## 位置策略

项目不做实时 GPS 追踪。每台设备只保存最新位置：

1. 默认城市和手动经纬度
2. 网页点击“获取位置”或手动更新
3. 快捷指令可调用 `POST /api/devices/{id}/location`
4. IP 粗定位不默认启用，可作为后续显式兜底能力

浏览器定位只在用户点击按钮时执行一次，系统只保存最新位置，不保存轨迹。

请求示例：

```bash
curl -X POST http://服务器IP:18761/api/devices/1/location \
  -H 'Content-Type: application/json' \
  -d '{"default_city":"成都双流","latitude":30.58,"longitude":103.92}'
```

## 配置备份和迁移

管理页可创建 SQLite 备份；API 也支持导出和导入设备配置。

导出配置会包含 Bark Key 和 Webhook URL，文件应按私密配置保存：

```bash
curl -H "Authorization: Bearer $EEW_AUTH_TOKEN" \
  http://服务器IP:18761/api/config/export
```

导入配置前系统会自动备份当前 SQLite：

```bash
curl -X POST http://服务器IP:18761/api/config/import \
  -H "Authorization: Bearer $EEW_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d @config.json
```

## 模拟演练

管理页选择一个历史地震场景后点击“开始演练”。系统会完整跑一遍判断、Bark 推送、独立详情页、地图和日志记录。

## 三类记录

- 实时地震记录：系统从已连接实时源收到的地震，小震、远震也会显示。
- 预警历史：从实时地震记录中筛选出进入预警判断链路的事件。
- 推送历史：预警历史里实际发送到 Apple 设备的通知结果。

## 全球特大地震

全球特大地震使用 EMSC/SeismicPortal standing order WebSocket。默认只处理 `M7.5+`，用户离震中很远时按最温和等级提醒，并且不显示本地横波倒计时；如果设备确实在震中附近，则按本地距离、烈度和到达状态展示。

## 系统配置

管理页的“系统配置”可以直接调整：

- 启用哪些 Wolfx 国内源
- 是否启用 EMSC 全球特大地震源
- 全球特大地震最低推送震级
- 红 / 黄 / 蓝分级阈值
- Bark 的 `level`、音量、铃声和重复次数

保存后系统会自动重连监听源。`.env` 里的同名配置只作为首次启动默认值和兜底。

## Wolfx 消息适配

不同 Wolfx 端点的消息字段可能不完全一致。当前适配常见字段：

- 事件 ID：`EventID`、`eventId`、`id`
- 震中：`HypoCenter`、`Epicenter`、`location`
- 经纬度：`Latitude` / `Longitude`、`lat` / `lon`
- 震级：`Magnitude`、`Mag`
- 深度：`Depth`
- 发震时间：`OriginTime`、`Time`
- 报数：`ReportNum`、`Serial`

如果实际端点字段不同，只需要扩展 `app/wolfx.py` 的 `normalize_wolfx_message`。

## 隐私

不要提交 `.env`、`data/`、SQLite 数据库、真实 Bark Key、真实手机号或私有账号。

本项目不做实时 GPS 追踪，只保存每台设备的最新位置。

仓库内置两层常规检查：

- GitHub Actions：每次 push / pull request 自动运行隐私检查、前端构建、Python 编译和 pytest。
- 本地 pre-commit：运行下面命令后，每次 `git commit` 前自动执行隐私检查。

```bash
./scripts/install_git_hooks.sh
python3 scripts/privacy_check.py
```

## 测试

```bash
python3 -m compileall app scripts tests
python3 scripts/privacy_check.py
docker compose run --rm -v "$PWD:/src" --entrypoint sh eew-hub \
  -c "cd /src && pip install -r requirements-dev.txt && PYTHONPATH=/src pytest"
```

## License

MIT
