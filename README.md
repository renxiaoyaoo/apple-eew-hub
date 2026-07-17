# Apple 设备地震预警系统

一个可自部署的私有地震预警中枢。它监听实时地震源，在本地判断是否需要提醒，并把预警推送到 iPhone、iPad 或家庭屏幕。

项目可以运行在任意 Docker 主机上：家用服务器、NAS、迷你主机、树莓派或云服务器都可以。

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

- 管理页：`http://服务器IP:18761/`
- Bark Server：`http://服务器IP:18762/`

详细步骤见 [QUICKSTART.md](./QUICKSTART.md)。

## Bark 可用可不用

推荐使用自建 Bark Server，因为 iPhone 上提醒效果最好。Docker Compose 默认会启动 `bark-server`，Bark App 里填你的 Bark Server 地址后，复制设备 Key 到管理页即可。

如果不用 Bark，可以：

- 用 `ntfy`
- 用 `Webhook`
- 不配置推送设备，只查看实时地震记录、预警历史、演练、地图和独立预警页

## 三类记录

- 实时地震记录：系统从实时源收到的地震，小震和远震也会显示。
- 预警历史：进入本地判断链路的事件。
- 推送历史：实际发送到设备的通知结果。

## 位置和隐私

- 每台设备只保存最新位置。
- 浏览器定位只在点击“获取位置”时执行。
- 不保存位置轨迹。
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
python3 -m py_compile app/*.py scripts/privacy_check.py tests/*.py
docker compose run --rm -v "$PWD:/src" --entrypoint sh eew-hub \
  -c "cd /src && pip install -r requirements-dev.txt && PYTHONPATH=/src pytest"
```

## License

MIT
