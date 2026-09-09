# Apple 设备地震预警系统

一个可自部署的私有地震预警中枢。它监听实时地震源，在本地判断是否需要提醒，并把预警推送到 iPhone、iPad 或家庭屏幕。

项目可以运行在任意 Docker 主机上：家用服务器、NAS、迷你主机、树莓派或云服务器都可以。

开源地址：https://github.com/renxiaoyaoo/apple-eew-hub

## 主要特点

- 自带可选的自建 Bark Server，适合 iPhone 强提醒。
- Bark 不是必需，也支持 ntfy 和 Webhook。
- 每台 Apple 设备可单独设置位置、震级、距离和烈度阈值。
- 不做实时 GPS 追踪，只保存每台设备的最新位置。
- 提供安卓风格预警卡片、倒计时、地图、演练和历史记录。
- 支持国内 Wolfx EEW 源和 EMSC 全球特大地震源。

## 快速启动

```bash
cp example.env .env
docker compose up -d --build
```

打开：

- 管理页：`http://127.0.0.1:18761/`
- Bark Server：`http://127.0.0.1:18762/`

详细步骤见 [QUICKSTART.md](./QUICKSTART.md)。

## 公网访问和认证

默认适合在家庭内网使用。管理页和 Bark Server 如果要暴露到公网，推荐放在 Cloudflare Access、反向代理登录或 VPN 后面。

Docker 默认只监听宿主机本地地址。需要从可信局域网直接访问时，在 `.env` 中将 `EEW_BIND_ADDRESS` 和 `BARK_BIND_ADDRESS` 设为 `0.0.0.0`。

网页导出的配置不包含 Bark Key、ntfy 地址或 Webhook 地址。完整备份和恢复请使用系统生成的 SQLite 备份。

`EEW_AUTH_TOKEN` 是内置 API 口令兜底：设置后，网页会要求输入口令，除 `/api/health` 外的 API 都需要 Bearer Token。它不是完整账号系统，也不替代 Cloudflare Access。

## Bark 可用可不用

推荐使用自建 Bark Server，因为 iPhone 上提醒效果最好。Docker Compose 默认会启动 `bark-server`，Bark App 里填你的 Bark Server 地址后，复制设备 Key 到管理页即可。

如果不用 Bark，可以：

- 用 `ntfy`
- 用 `Webhook`
- 不配置推送设备，只查看收到的地震、触发的预警、演练、地图和独立预警页

## 三个页面怎么理解

- 收到的地震：系统从实时源听到的事件，不代表危险。
- 触发的预警：符合设备位置和阈值、需要提醒你的地震。
- 发出的通知：Bark、ntfy 或 Webhook 实际发送后的结果。

## 推荐提醒规则

- 家庭设备建议从 `M4.5+ / 500km 内 / 烈度2+` 开始。
- 红色：高烈度，本地强提醒，发现时持续响；如横波尚未到达，到达时再发一次。
- 黄色：本地明显有感，使用 Bark 最高级强提醒，但不持续响；如横波尚未到达，到达时再发一次。
- 蓝色：普通提醒。
- 本地或近场地震只要达到设备的震级和距离条件，就至少发蓝色提醒；烈度主要决定提醒强度。
- 远场全球或日本气象厅大震不显示本地倒计时；M7.0 以下远场只记录。

## 位置和隐私

- 每台设备只保存最新位置。
- 浏览器定位只在点击“获取位置”时执行。
- 不保存位置轨迹。
- 公网访问建议使用 Cloudflare Access / VPN / 反向代理认证。
- 不要提交 `.env`、`data/`、SQLite 数据库、真实 Bark Key、手机号、账号或 token。

## 隐私检查机制

仓库内置常规检查：

- GitHub Actions：每次 push / pull request 自动运行隐私检查、前端构建、Python 编译和 pytest。
- 本地 pre-commit：安装后，每次提交前自动运行隐私检查。

安装本地钩子：

```bash
./scripts/install_git_hooks.sh
```

手动检查：

```bash
python3 scripts/privacy_check.py
```

## 测试

```bash
npm run build
npm run typecheck
python3 -m py_compile app/*.py scripts/privacy_check.py tests/*.py
docker compose run --rm -v "$PWD:/src" --entrypoint sh eew-hub \
  -c "cd /src && pip install -r requirements-dev.txt && PYTHONPATH=/src pytest"
```

前端静态文件由 `npm run build` 或 Docker 构建生成到 `public/`，不提交到仓库。

## License

MIT
