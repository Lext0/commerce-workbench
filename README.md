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

服务启动和健康检查。
