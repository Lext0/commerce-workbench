# 商品工作台

用于商品管理和批量铺货，以及知识维护和客服售后。

## 环境

Python 3.12 或更高版本。

## 安装与运行

在项目目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m commerce_workbench
```

默认地址为 http://127.0.0.1:8787，健康检查接口为 `/api/health`。

Linux 和 macOS 使用 `.venv/bin/python` 替代 Windows 的 Python 路径。

## 检查

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 当前功能

服务启动和健康检查，以及工作台名称保存。数据保存在 SQLite 中。

## 配置

程序读取 `CW_HOST` 和 `CW_PORT`，以及 `CW_DATA_DIR` 环境变量。`.env.example` 列出可用配置，程序不会自动读取 `.env` 文件。

默认只监听本机地址，数据保存在启动目录的 `data` 中。重新启动时使用同一个数据目录。

```powershell
.\.venv\Scripts\python.exe -m commerce_workbench --port 8788 --data-dir D:\workbench-data
```
