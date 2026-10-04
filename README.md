# 栈灯：本地版与云端多人版

栈灯可以在个人电脑上本地运行，也可以配置为云端登录服务。云端模式要求账号登录；每个账号拥有独立的临时项目工作区，用户通过 ZIP 上传项目。AI 只会收到用户勾选的文件。

## 本地运行

需要 Python 3.10 或更新版本，并准备模型服务 API Key。

```powershell
$env:OPENAI_API_KEY = "你的 API Key"
Set-Location "local-coding-assistant 文件夹路径"
.\启动助手.ps1
```

本地模式默认只服务本机浏览器。启动脚本会打开 `http://127.0.0.1:8765`。首次运行安装依赖。模型请求会把所选文件内容发送至已配置的模型服务。

## 云端模式所需服务

公开注册和 AI 用量控制依赖 Supabase Auth 与 Supabase Postgres。云端 AI 密钥必须由部署平台作为服务端密钥保存，不能放在 HTML、JavaScript、代码仓库或浏览器设置中。

1. 创建 Supabase 项目。
2. 在 Supabase SQL Editor 中运行 [`supabase/schema.sql`](supabase/schema.sql)。该脚本创建账号套餐与月度请求额度表、注册用户资料触发器，以及服务器专用的额度预留函数。
3. 在 Supabase Auth 设置中配置允许的注册方式和生产站点 URL。邮箱确认模板需把验证链接返回到站点根路径，并附上 `token_hash` 与 `type=signup` 查询参数，供栈灯服务端完成验证；不要改成把访问令牌放入网页 URL 片段。
4. 将代码推送至私有 Git 仓库，并用支持 Docker 的云平台部署。
5. 在云平台设置以下环境变量：

   | 变量 | 用途 |
   | --- | --- |
   | `APP_MODE` | 必须为 `public` |
   | `SUPABASE_URL` | Supabase 项目 URL |
   | `SUPABASE_ANON_KEY` | Supabase 公共 anon key；服务端用于调用 Auth |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase 服务端密钥；仅服务器可见，具备高权限 |
   | `OPENAI_API_KEY` | 当前部署所使用模型服务的服务端密钥 |
   | `OPENAI_MODEL` | 部署所用模型名 |
   | `OPENAI_BASE_URL` | 可选；兼容 OpenAI Responses API 的服务端点 |

6. 部署后使用 HTTPS，并把生产域名加入 Supabase Auth 的站点与回调 URL 配置。

Docker 启动命令会绑定 `0.0.0.0` 并读取平台提供的 `PORT`。环境变量样例见 [`.env.example`](.env.example)。不要把真实密钥写进该文件。

## 云端行为与限额

- 邮箱和密码交由 Supabase Auth 验证；浏览器只保存 HttpOnly、Secure、SameSite Cookie，服务端按需刷新会话。
- 用户工作区按 Supabase 用户 ID 隔离。ZIP 上限为 25 MB，展开后不超过 100 MB、最多 5000 个文件；拒绝目录穿越和符号链接。`.git`、依赖目录及 `.env` 文件不会导入。
- 云端工作区 24 小时无访问后会清除。多数云平台的临时磁盘也可能在重启或重新部署时清空；用户应保留本地项目副本。
- 新账号默认每月最多 20 次 AI 请求。额度以“请求次数”计，不是 token 成本；套餐和额度由数据库控制，额度服务不可用时会拒绝 AI 请求。
- 模型调用错误不会向浏览器返回供应商内部错误。所选代码会发给当前云端配置的模型服务，部署前应在隐私说明中明确告知用户。

## 分地区运营

当前云端模式已预留 OpenAI 兼容的 `OPENAI_BASE_URL` 配置，但一个部署仍只连接一个模型端点。OpenAI 当前 API 支持地区列表不包含中国大陆；不得把当前 OpenAI API 部署用于向不支持地区提供访问。面向中国大陆和海外用户正式运营前，应分别确定各地区可用的模型服务、部署位置、备案及收款主体，再按地区部署或路由。环境变量切换只适合兼容 OpenAI Responses API 的服务，并不自动保证某个地区的可用性或合规性。

真实月费支付尚未接入。`profiles` 表已包含套餐、订阅状态、支付渠道和订阅 ID 字段；后续应增加经签名校验的支付回调，再由服务器更新这些字段。不能通过浏览器付款成功页直接授予会员。

## 安全说明

- 公开模式要求登录并启用数据库额度检查；缺少 Supabase 或额度配置时，公开登录/AI 功能会关闭或失败关闭。
- 服务端 API Key 和 Supabase service role key 只能配置在托管平台的加密环境变量中。
- 服务不执行上传项目中的程序。用户点击“应用修改”后只写回该账号的工作区文件。
- 公网部署前仍需配置 HTTPS、域名、Supabase 邮件验证与生产安全策略，并确定适用的地区运营要求。
