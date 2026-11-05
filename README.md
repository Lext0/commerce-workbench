# 商品工作台

用于商品管理和批量铺货，以及知识维护和客服售后。

## 环境

Python 3.12 或更高版本。

## 安装与运行

在项目目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m commerce_workbench
```

默认地址为 http://127.0.0.1:8787，健康检查接口为 `/api/health`。

Linux 和 macOS 使用 `.venv/bin/python` 替代 Windows 的 Python 路径。

## 检查

```powershell
.\.venv\Scripts\python.exe scripts/check.py
```

## 当前功能

首页与导航，以及工作台名称设置。

商品管理支持新建和编辑，可以按名称或型号搜索，也可以按分类查找。商品型号不能重复。售价和说明等资料可以稍后补充，已有内容在其他页面修改后会阻止旧页面覆盖。

从导航进入商品管理，点击新建商品，填写名称和型号后保存。在列表中点击商品名称或编辑可以继续修改。

保存商品后可以上传一张 JPEG、PNG 或 WebP 图片（最大 3 MB），也可以替换或删除。图片与商品资料一起保存在 SQLite 中。服务启动时自动初始化并升级数据结构。商品发布和批量铺货等功能继续开发。

## 配置

程序读取 `CW_HOST` 和 `CW_PORT`，以及 `CW_DATA_DIR` 环境变量。`.env.example` 列出可用配置，程序不会自动读取 `.env` 文件。

默认只监听本机地址，数据保存在启动目录的 `data` 中。重新启动时使用同一个数据目录。

```powershell
.\.venv\Scripts\python.exe -m commerce_workbench --port 8788 --data-dir D:\workbench-data
```
