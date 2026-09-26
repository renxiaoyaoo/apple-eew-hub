# Quick Start

## 1. 启动

```bash
cd apple-eew-hub
cp example.env .env
docker compose up -d --build
```

检查：

```bash
docker compose ps
curl http://127.0.0.1:18761/api/health
```

打开管理页：

```text
http://127.0.0.1:18761/
```

## 2. 添加 Apple 设备

推荐使用 Bark：

1. Bark App 的服务器填你的自建 Bark Server 地址。
2. 本机地址是 `http://127.0.0.1:18762`；通过 Cloudflare Tunnel 使用时填写 Bark 的公网域名。
3. 有公网时可以填 `https://bark.example.com`。
4. 在 Bark App 里复制 Key。
5. 回到管理页，保存 Apple 设备。
6. 点击“测试通知”。

不用 Bark 也可以，设备推送方式可选 `ntfy` 或 `webhook`。

## 3. 设置位置

每台设备都可以单独设置位置：

- 填城市
- 点击“获取位置”
- 手动填经纬度

系统只保存最新位置，不保存轨迹。

## 4. 演练

在管理页选择历史地震场景，点击“开始演练”。

演练会完整跑一遍：

- 判断
- 推送
- 预警卡片
- 地图
- 历史记录

## 5. 实时源

默认不需要填写 `WOLFX_WS_URL`。

常用国内源：

```env
WOLFX_WS_BASE=wss://ws-api.wolfx.jp
WOLFX_SOURCES=sc_eew,cq_eew,cenc_eew,cenc_eqlist,jma_eew
```

`cenc_eqlist` 是事件驱动的中国地震台网正式速报 WebSocket，用于在 EEW 流漏报时补充记录和通知，不是定时拉取。

服务器访问 Wolfx 必须经过 HTTP 代理时，可以设置：

```env
EEW_WEBSOCKET_PROXY=http://host.docker.internal:7890
```

全球特大地震源：

```env
GLOBAL_QUAKE_SOURCE_URL=wss://www.seismicportal.eu/standing_order/websocket
GLOBAL_QUAKE_MIN_MAGNITUDE=7.0
GLOBAL_FAR_ALERT_ENABLED=1
```

远场全球地震只做温和提醒，不显示本地倒计时。

系统默认会在任一已启用实时源连续离线 1 小时后，通过现有设备通道发送一次异常通知；全部恢复后再发送一次恢复通知。可在系统配置中关闭。

## 6. 公网访问

只在家里用，不需要公网。

如果要在外面访问管理页或让 Bark App 访问自建 Bark Server，可以用 Cloudflare Tunnel、frp 或反向代理。

默认端口只绑定 `127.0.0.1`。需要让可信局域网设备直接连接时，在 `.env` 中设置：

```env
EEW_BIND_ADDRESS=0.0.0.0
BARK_BIND_ADDRESS=0.0.0.0
```

推荐做法：

- 管理页放在 Cloudflare Access、VPN 或反向代理登录后面。
- Bark Server 可以单独暴露给 Bark App 使用。
- `EEW_AUTH_TOKEN` 作为内置 API 口令兜底，不替代 Cloudflare Access。

建议至少设置：

```env
EEW_AUTH_TOKEN=换成一段足够长的随机字符串
PUBLIC_BASE_URL=https://eew.example.com
BARK_BASE_URL=http://bark-server:18762
```

设置 `EEW_AUTH_TOKEN` 后，网页会要求输入这个口令；除健康检查外，API 都会被保护。

Bark App 里填写外部地址：

```text
https://bark.example.com
```

## 7. 常用命令

```bash
docker compose logs -f eew-hub
docker compose logs -f bark-server
docker compose restart
docker compose up -d --build
```
