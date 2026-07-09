# Quick Start

目标：树莓派上一次启动两个服务：

- `eew-hub`：地震预警判断和 Web 管理页
- `bark-server`：自建 Bark Server

默认四川优先接入 Wolfx 当前公开 WebSocket：

- `wss://ws-api.wolfx.jp/sc_eew`：四川省地震局，四川优先
- `wss://ws-api.wolfx.jp/cq_eew`：重庆市地震局，覆盖川渝周边
- `wss://ws-api.wolfx.jp/cenc_eew`：中国地震台网，全国补充

全球特大地震接入 EMSC/SeismicPortal WebSocket：

- `wss://www.seismicportal.eu/standing_order/websocket`：全球新事件和更新，默认只处理 `M7.5+`

## 1. 启动

```bash
cd /home/pi/apps/projects/raspi-eew-hub
cp example.env .env
docker compose up -d --build
```

检查：

```bash
docker compose ps
curl http://127.0.0.1:18761/api/health
curl http://127.0.0.1:18762/ping
```

打开管理页：

```text
https://h-eew.111184.xyz/
```

预警详情页不需要手动打开。Bark 通知会指向这次地震的独立页面 `/event/{event_id}`。

## 2. 设置管理 Token

编辑 `.env`：

```env
EEW_AUTH_TOKEN=换成一段足够长的随机字符串
```

重启：

```bash
docker compose up -d
```

刷新管理页后，在“管理 Token”输入同一段字符串。

## 3. iPhone Bark App 连接自建 Server

优先使用 Cloudflare 地址：

```text
https://h-bark.111184.xyz
```

局域网备用：

```text
http://树莓派IP:18762
```

在 Bark App 中切换到这个服务器后，复制设备 Key。回到 EEW Hub 管理页添加设备：

- 推送方式：`Bark`
- Bark Key：Bark App 里复制的 Key
- 默认城市：例如 `成都`
- 经纬度：点击“获取位置”，或手动填写设备常驻位置
- 阈值：先用默认 `M≥4.5`、`500km`、`烈度≥2`

保存后点击“发送测试通知”。iPhone 能响，才继续下一步。

浏览器定位只在你点击按钮时执行一次，系统只保存最新经纬度，不保存轨迹。iPhone/Safari 通常要求 HTTPS 或局域网可信上下文；如果浏览器拒绝定位，可以在地图 App 里复制当前位置经纬度后手动填写。

## 4. 历史地震演练

管理页选择一个历史地震场景，点击“开始演练”。

预期结果：

- iPhone 收到 Bark 通知
- 点击通知打开这次演练的独立预警详情页
- 详情页显示分级预警卡片和地图
- 日志页出现演练事件和推送结果

## 5. Wolfx 实时监听

默认不需要填写 `WOLFX_WS_URL`。系统会按 `.env` 中的：

```env
WOLFX_WS_BASE=wss://ws-api.wolfx.jp
WOLFX_SOURCES=sc_eew,cq_eew,cenc_eew
```

自动连接四川优先的国内源。状态页里看到 `sc_eew`、`cq_eew`、`cenc_eew` 至少一个 `connected` 即可；正常情况下三个都会连接。

只有当 Wolfx 端点变化或你要连自定义代理时，才设置：

```env
WOLFX_WS_URL=wss://你的自定义端点
```

多个自定义端点可用英文逗号分隔。

## 6. 全球特大地震源

默认不需要配置。系统会连接：

```env
GLOBAL_QUAKE_SOURCE_URL=wss://www.seismicportal.eu/standing_order/websocket
GLOBAL_QUAKE_MIN_MAGNITUDE=7.5
```

这不是本地倒计时 EEW。远距离全球特大地震只做温和提醒；如果设备位置确实靠近震中，才按本地距离和烈度展示预警。

这些参数也可以在网页“系统配置”里改。常用项默认展开，源地址、音量、铃声和重复间隔放在“高级配置”里。

## 7. 公网访问建议

如果只是家庭局域网使用，不需要公网。

如果 iPhone 在外面也要访问管理页或预警页：

- `18761`：EEW Hub 管理页，必须设置 `EEW_AUTH_TOKEN`
- `18762`：Bark Server，Bark App 必须能访问它

当前已配置两个 Cloudflare 域名：

```env
PUBLIC_BASE_URL=https://h-eew.111184.xyz
BARK_BASE_URL=http://bark-server:18762
```

Bark App 的服务器地址填：

```text
https://h-bark.111184.xyz
```

注意：`BARK_BASE_URL` 是 EEW Hub 容器访问 Bark Server 的内部地址，默认不要改；Bark App 里填写的是手机能访问的外部地址。

Cloudflare Zero Trust Tunnel 准备好了 `cloudflared` 服务。拿到 Tunnel token 后填入 `.env`：

```env
CLOUDFLARED_TOKEN=你的 Cloudflare Tunnel token
```

然后启动：

```bash
docker compose --profile tunnel up -d
```

当前 Tunnel 已添加两个 Public Hostname：

- `h-eew.111184.xyz` -> `http://localhost:18761`
- `h-bark.111184.xyz` -> `http://localhost:18762`

## 8. 常用命令

```bash
docker compose logs -f eew-hub
docker compose logs -f bark-server
docker compose restart
docker compose pull bark-server
docker compose up -d --build
```

备份：

```bash
curl -X POST http://127.0.0.1:18761/api/backup \
  -H "Authorization: Bearer $EEW_AUTH_TOKEN"
```
