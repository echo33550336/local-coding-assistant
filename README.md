# 栈灯｜基于 DeepSeek 的 AI 编程助手

栈灯把 AI 带进本地项目：选择需要参考的文件，描述开发任务，查看生成的改动差异后，再决定是否应用。项目文件默认在本机读取和写回；只有你勾选的文件会发送给 DeepSeek API。

默认使用 DeepSeek API 和 `deepseek-flash` 模型。本地使用不需要注册栈灯账号或部署服务器；也可以配置 Supabase 启用云端账号模式。这个仓库提供源代码，在线服务需要自行部署。

## 能做什么

- 浏览项目文件，并按需选择要提供给模型的文件。
- 请 AI 梳理代码、排查问题、实现小功能或补充文档。
- 先查看完整改动，再决定是否应用到项目。
- 在需要时配置 Supabase，启用云端登录和按账号隔离的临时工作区。

## 本地启动

需要 Python 3.10 或更新版本，以及 DeepSeek API Key。第一次启动时会安装项目依赖。

在 PowerShell 中运行：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
Set-Location "local-coding-assistant 文件夹路径"
.\启动助手.ps1
```

栈灯会打开 `http://127.0.0.1:8765`。默认模型是 `deepseek-flash`，API 地址是 `https://api.deepseek.com`。需要时可以在启动前设置 `DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL` 或 `DEEPSEEK_REASONING_EFFORT`。可参考 [`.env.example`](.env.example) 配置变量；不要把真实密钥提交到 GitHub。

栈灯只会把你勾选的文本文件内容发送到所配置的模型服务。不要选择包含密码、访问令牌、客户资料等敏感信息的文件。模型输出也可能有误，应用前请检查 diff。

DeepSeek API 使用兼容 OpenAI Responses API 的请求格式。接口地址、模型名称和参数以 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/) 为准。

## 云端部署（可选）

云端模式需要 Supabase Auth 与 Postgres。数据库初始化脚本位于 [`supabase/schema.sql`](supabase/schema.sql)。部署前先在 Supabase 配好注册方式、邮件验证及正式站点地址，再将项目部署到支持 Docker 的平台，并配置以下服务端环境变量：

| 变量 | 用途 |
| --- | --- |
| `APP_MODE` | 设置为 `public` 以启用云端账号模式 |
| `SUPABASE_URL` | Supabase 项目地址 |
| `SUPABASE_ANON_KEY` | Supabase 公共 anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase 服务端密钥，只能保存在部署平台的服务端环境变量中 |
| `DEEPSEEK_API_KEY` | DeepSeek 服务端 API Key |
| `DEEPSEEK_MODEL` | 模型名称，默认 `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | API 地址，默认 `https://api.deepseek.com` |
| `DEEPSEEK_REASONING_EFFORT` | 推理强度，默认 `low` |

Docker 启动时会监听平台提供的 `PORT`。公网部署请启用 HTTPS，并将生产域名加入 Supabase Auth 的站点和回调配置。模型密钥和 Supabase service role key 不能放进网页代码、客户端配置或公开仓库。

云端模式下，用户通过 ZIP 上传项目；每个账号有独立的临时工作区。ZIP 最大 25 MB，解压后最多 100 MB、5000 个文件。工作区连续 24 小时无访问后会清理。新账号默认每月可发起 20 次 AI 请求；目前按请求次数计量，真实月费支付尚未接入。

## 项目结构与技术栈

- Python、FastAPI、Uvicorn：本地和云端服务。
- HTML、CSS、JavaScript：网页界面。
- OpenAI Python SDK：调用 DeepSeek 兼容的 Responses API。
- Supabase Auth、Postgres：云端模式的登录与额度管理（可选）。
- Docker：云端部署（可选）。

## 开发提示

- 本地模式默认只绑定 `127.0.0.1`，仅本机可访问。
- 服务不会执行项目里的程序；应用修改时只写入允许的工作区文件。
- 云端模型调用会把所选代码发送至部署配置的 DeepSeek API 账号。上线前应明确告知使用者数据处理方式，并按需设置隐私说明和服务条款。
- 会员支付、套餐自动续费和支付回调目前未实现。
