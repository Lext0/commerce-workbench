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

保存商品后可以上传一张 JPEG、PNG 或 WebP 图片（最大 3 MB），也可以替换或删除。商品填写大于零的售价并上传图片后，可发布到本地模拟店铺，查看状态或撤回；发布记录保存当时的商品快照。图片与商品资料保存在 SQLite 中，服务启动时自动初始化并升级数据结构。

一键铺货支持搜索已有商品加入清单，或输入新型号复制商品并复制图片。CSV 按页面模板使用 UTF-8 编码，导入后新商品进入清单；失败行显示原因。勾选商品后发布，已发布的型号跳过，缺少图片或售价的商品会显示失败原因；补全后可在批次记录中单独重试，成功的商品不会重复发布。批次和逐件结果保存在数据库中。

报价核算使用人民币成本和运费、人民币兑美元汇率、费用比例及利润比例，按（成本 + 运费）÷ 汇率 ÷（1 − 费用比例 − 利润比例）计算美元报价。结果仅供参考，不会自动改写商品售价，汇率由使用者填写。

商品编辑页可根据已保存的名称、型号、分类和说明整理文案草稿。此功能使用固定模板，不调用 AI；草稿放入编辑区后需要人工核对并保存。

## 配置

程序读取 `CW_HOST` 和 `CW_PORT`，以及 `CW_DATA_DIR` 环境变量。`.env.example` 列出可用配置，程序不会自动读取 `.env` 文件。

默认只监听本机地址，数据保存在启动目录的 `data` 中。重新启动时使用同一个数据目录。

```powershell
.\.venv\Scripts\python.exe -m commerce_workbench --port 8788 --data-dir D:\workbench-data
```
