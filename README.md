# YKB-MCP

医考帮（yikaobang）个人账号数据 MCP 服务器。让 AI Agent（WorkBuddy、千问办公、豆包工作、Codex 等任何支持 MCP 的客户端）读取你在医考帮的**评论、评论点赞、错题、收藏、笔记、已斩题目**，并支持少量写操作（点赞评论、发表评论、斩题）。

> **版权与免责声明**：
> - 「医考帮」「Yikaobang」商标、官方 App 及题库内容的版权均归**北京医考帮教育**及相关权利人所有。
> - 本项目为**非官方**开源工具，与医考帮官方无任何关联，未获其背书或赞助；名称中的「医考帮」仅用于描述工具用途（指示性合理使用）。
> - 本工具仅读取**你自己账号**的数据、辅助个人学习，不提供题库内容的传播；请遵守医考帮用户协议与相关法律法规，内置限速以避免对官方服务器造成压力。使用风险自负。
> - [MIT 许可证](LICENSE)仅覆盖本项目代码，不延伸至官方商标、App 或题库内容。

## 功能一览

| 分组 | 工具 | 说明 |
|---|---|---|
| 账号 | `ykb_login` | 打开本地网页登录（127.0.0.1 一次性页面），密码不经过 AI 对话 |
| 账号 | `ykb_login_status` | 查询网页登录进度/结果 |
| 账号 | `ykb_whoami` / `ykb_logout` | 登录状态与缓存统计 / 退出 |
| 账号 | `ykb_identities` | 身份树（可用题库：临床期末、口腔期末、执业医师等） |
| 做题 | `ykb_answer_records` | 做题记录，`filter=wrong\|cut\|right\|all`（错题/已斩/做对） |
| 题目 | `ykb_chapters` | 科目/章节目录（含题量） |
| 题目 | `ykb_chapter_questions` | 整章题目（DES 解密：题干/选项/答案/收藏/已斩标记） |
| 题目 | `ykb_question` | 单题详情（缓存优先，含解析） |
| 收藏 | `ykb_collections` | 收藏列表（缓存优先 + 实验性接口探测） |
| 收藏 | `ykb_collections_scan` | 按章节扫描收藏标记（限速、断点续传） |
| 评论 | `ykb_comments` | 题目热门评论（最多点赞/最高热度/最多回复/最新） |
| 评论 | `ykb_my_praises` / `ykb_my_comments` | 某题下我点赞的 / 我发表的评论 |
| 评论 | `ykb_my_praises_all` / `ykb_my_comments_all` | **全局**我点赞的 / 我发表的评论（缓存+增量扫描） |
| 笔记 | `ykb_notes` / `ykb_notes_all` | 某题笔记 / 全局笔记归纳 |
| 同步 | `ykb_sync` | 批量同步点赞/评论/笔记到本地缓存（限速、可续跑） |
| 搜索 | `ykb_search_local` | 本地缓存全文搜索（题干/评论/笔记） |
| 写 | `ykb_praise_comment` | 【写】点赞评论 |
| 写 | `ykb_publish_comment` | 【写】发表评论 |
| 写 | `ykb_cut_question` | 【写】斩题/取消斩题 |

## 安装

需要 Python ≥ 3.10。推荐 [uv](https://docs.astral.sh/uv/)：

```bash
git clone https://github.com/pkx07/YKB-MCP.git
cd YKB-MCP
uv sync
```

## 配置 MCP 客户端

以下示例中的 `/path/to/YKB-MCP` 替换为本仓库的实际绝对路径。任何支持 stdio MCP 的客户端均可接入。

### WorkBuddy（腾讯）

编辑用户级配置 `~/.workbuddy/mcp.json`（所有项目复用；仅当前项目生效则用 `<项目目录>/.workbuddy/mcp.json`）：

```json
{
  "mcpServers": {
    "ykb": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/YKB-MCP", "ykb-mcp"]
    }
  }
}
```

也可在界面操作：侧边栏 **插件** → 右上角 **MCP 服务器** → **配置 MCP**，粘贴上述 JSON 保存。状态灯绿色即连接成功。官方文档：[MCP 配置指南](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)。

### 千问办公 QwenWork（阿里）

桌面客户端 → 左侧导航 **扩展** → **连接器** → 右上角 **+ 添加**：

- **手动填写配置**：服务器类型选 **STDIO**，服务器名称填 `ykb`，命令填完整启动命令：

  ```
  uv run --directory /path/to/YKB-MCP ykb-mcp
  ```

- 或 **粘贴 JSON 配置**：

  ```json
  {
    "mcpServers": {
      "ykb": {
        "command": "uv",
        "args": ["run", "--directory", "/path/to/YKB-MCP", "ykb-mcp"]
      }
    }
  }
  ```

注意：添加/启用后需**新建一个对话任务**才会生效。官方文档：[连接器 · 自定义 MCP 服务](https://docs.qwenwork.cn/features/connectors#%E8%87%AA%E5%AE%9A%E4%B9%89-mcp-%E6%9C%8D%E5%8A%A1)。

### 豆包工作（字节跳动）

客户端 → 左侧 **插件·技能·伙伴** → **插件** 页右上角 **+ 添加** → **新建自定义连接器**：

- 服务器名称：`ykb`
- 传输类型：**STDIO**
- 运行命令：`uv`
- 参数：`run --directory /path/to/YKB-MCP ykb-mcp`
- 环境变量：无需填写

保存后在任务中直接描述需求，或用 `/`、`@` 指定插件。官方文档：[使用插件](https://www.doubao.com/work/docs/zh-cn/articles/705018132598-plugins#tabs0|lineguid-oebEe)。

### Codex（OpenAI）

编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.ykb]
command = "uv"
args = ["run", "--directory", "/path/to/YKB-MCP", "ykb-mcp"]
```

也可以 `uv pip install -e .` 后直接使用 `ykb-mcp` 命令（stdio 传输）。

## 使用流程

1. 对 Agent 说「登录医考帮」，调用 `ykb_login()` 会在本机启动一个**仅 127.0.0.1 可访问的一次性登录页**并自动打开浏览器。手机号和密码在浏览器里输入，由本地进程直接提交官方接口，**全程不经过 AI 对话**。登录成功后凭据保存在 `~/.ykb-mcp/credentials.json`（仅 token/secret/user_id，权限 600，**不存储密码**）。页面 5 分钟有效，连续失败 5 次自动关闭。
   - 也可以不经 agent 手动登录：`uv run ykb-mcp-login`
2. `ykb_identities` 查看题库身份 → `ykb_answer_records(identity_id, filter="wrong")` 拉错题。
3. `ykb_chapters` → `ykb_chapter_questions` 获取题目内容；`ykb_question` 查单题解析。
4. `ykb_my_praises_all` / `ykb_my_comments_all` / `ykb_notes_all` 全局归纳；首次调用会限速增量扫描，`remaining>0` 时重复调用续扫，或用 `ykb_sync` 批量同步。
5. `ykb_search_local` 在本地缓存中搜索。

### 数据与限速

- 缓存：`~/.ykb-mcp/cache.db`（SQLite）。可用环境变量 `YKB_MCP_HOME` 改目录。
- 所有请求自动限速约 1.2~2 秒/请求（`YKB_MCP_MIN_INTERVAL` / `YKB_MCP_JITTER` 可调），模拟正常刷题节奏，降低风控风险。
- 登录过期（业务码 309）会自动清除凭据并提示重新登录；203 表示章节无权限（VIP/题库未购买）。
- 官方没有「收藏/我的评论/我的点赞/笔记」的全局列表接口，只能按题拉取；本工具用「已做题集合 + 限速扫描 + 本地缓存」归纳，首次全量扫描较慢，请耐心续跑。

### 真实账号冒烟测试

```bash
uv run python -m ykb_mcp.smoke
```

密码在本机交互输入（getpass），只调用只读接口，验证登录/身份树/做题记录/章节解密/评论/笔记全链路。

## 开发

```bash
uv sync
uv run pytest
```

单元测试覆盖：签名算法（固定向量）、DES 解密（固定密文向量）、请求头/凭据注入/309 处理、缓存层、本地网页登录、以及基于 Mock 传输的全部 MCP 工具端到端测试。

协议与接口细节见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

## 许可证

[MIT](LICENSE)