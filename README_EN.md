# YKB-MCP

An MCP (Model Context Protocol) server for **Yikaobang (医考帮)**, a Chinese medical-exam prep app. It lets AI agents (WorkBuddy, QwenWork, Doubao Work, Codex — any MCP client) read **your own account data**: comments, comment likes, wrong questions, collections, notes, and "cut" (mastered) questions — plus a few write actions (like a comment, publish a comment, cut a question).

> **Copyright & disclaimer**:
> - The "医考帮" / "Yikaobang" trademarks, the official app, and all question-bank content are the property of **Beijing Yikaobang Education (北京医考帮教育)** and related rights holders.
> - This is an **unofficial** open-source tool. It is not affiliated with, endorsed by, or sponsored by the official operator. The name "Yikaobang" is used only to describe the tool's purpose (nominative fair use).
> - The tool reads **your own account data** for personal study only and does not redistribute question-bank content. Respect Yikaobang's terms of service and applicable laws; built-in rate limiting avoids pressuring official servers. Use at your own risk.
> - The [MIT license](LICENSE) covers this project's code only; it does not extend to official trademarks, the app, or question-bank content.

> [!IMPORTANT]
> Logging in through this MCP will **sign you out of the Yikaobang app on your phone and other devices** (due to the official account session mechanism). Be aware before logging in; to keep using the app, simply log in there again (which may in turn invalidate this MCP's session, requiring a re-login here).

## Tools

| Group | Tool | Description |
|---|---|---|
| Account | `ykb_login` | Opens a local one-time login page (127.0.0.1 only); the password never passes through the AI conversation |
| Account | `ykb_login_status` | Check web-login progress/result |
| Account | `ykb_whoami` / `ykb_logout` | Login status & cache stats / logout |
| Account | `ykb_identities` | Identity tree (available banks: clinical finals, stomatology, licensing exam, ...) |
| Records | `ykb_answer_records` | Answer records, `filter=wrong\|cut\|right\|all` |
| Questions | `ykb_chapters` | Subject/chapter directory with question counts |
| Questions | `ykb_chapter_questions` | Full chapter questions (DES-decrypted: stem/options/answer/collection/cut flags) |
| Questions | `ykb_question` | Single question detail (cache-first, with explanation) |
| Collections | `ykb_collections` | Collected questions (cache-first + experimental endpoint probe) |
| Collections | `ykb_collections_scan` | Scan chapters for collection flags (paced, resumable) |
| Comments | `ykb_comments` | Hot comments per question (most-liked / hottest / most-replied / newest) |
| Comments | `ykb_my_praises` / `ykb_my_comments` | My liked / my published comments for a question |
| Comments | `ykb_my_praises_all` / `ykb_my_comments_all` | **Global** my-likes / my-comments (cache + incremental scan) |
| Notes | `ykb_notes` / `ykb_notes_all` | Notes per question / global notes |
| Sync | `ykb_sync` | Bulk sync likes/comments/notes into local cache (paced, resumable) |
| Search | `ykb_search_local` | Full-text search over local cache |
| Write | `ykb_praise_comment` | [WRITE] Like a comment |
| Write | `ykb_publish_comment` | [WRITE] Publish a comment |
| Write | `ykb_cut_question` | [WRITE] Cut / uncut a question |

## Install

Python ≥ 3.10, [uv](https://docs.astral.sh/uv/) recommended:

```bash
git clone https://github.com/pkx07/YKB-MCP.git
cd YKB-MCP
uv sync
```

## MCP client configuration

Replace `/path/to/YKB-MCP` with the absolute path of this repository. Any MCP client with stdio support works.

### WorkBuddy (Tencent)

Edit the user-level config `~/.workbuddy/mcp.json` (shared across projects; for a single project use `<project>/.workbuddy/mcp.json`):

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

Or via the UI: sidebar **Plugins** → **MCP Servers** (top right) → **Configure MCP**, paste the JSON and save. A green status light means connected. Official guide: [MCP configuration](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide).

### QwenWork (Alibaba)

Desktop client → left nav **Extensions** → **Connectors** → **+ Add** (top right):

- **Manual config**: server type **STDIO**, name `ykb`, command (full launch command):

  ```
  uv run --directory /path/to/YKB-MCP ykb-mcp
  ```

- Or **Paste JSON config**:

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

Note: after adding/enabling a connector you must **start a new conversation** for it to take effect. Official docs: [Connectors · Custom MCP services](https://docs.qwenwork.cn/features/connectors#%E8%87%AA%E5%AE%9A%E4%B9%89-mcp-%E6%9C%8D%E5%8A%A1).

### Doubao Work (ByteDance)

Client → left nav **Plugins · Skills · Partners** → **Plugins** tab → **+ Add** (top right) → **New custom connector**:

- Server name: `ykb`
- Transport type: **STDIO**
- Command: `uv`
- Arguments: `run --directory /path/to/YKB-MCP ykb-mcp`
- Environment variables: none needed

Then describe your task in a conversation, or pick the plugin via `/` or `@`. Official docs: [Using plugins](https://www.doubao.com/work/docs/zh-cn/articles/705018132598-plugins#tabs0|lineguid-oebEe).

### Codex (OpenAI)

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.ykb]
command = "uv"
args = ["run", "--directory", "/path/to/YKB-MCP", "ykb-mcp"]
```

You can also `uv pip install -e .` and use the `ykb-mcp` command directly (stdio transport).

## Usage

1. Ask your agent to log in: `ykb_login()` starts a **one-time login page bound to 127.0.0.1** and opens your browser. You type your mobile number and password in the browser; the local process submits them directly to the official API — **they never pass through the AI conversation**. On success, credentials (token/secret/user_id only) are saved to `~/.ykb-mcp/credentials.json` with mode 600; the password is never stored. The page expires after 5 minutes or 5 failed attempts.
   - **Note: logging in will sign you out of the Yikaobang app on your phone and other devices.** Confirm before proceeding.
   - Manual login without an agent: `uv run ykb-mcp-login`
2. `ykb_identities` → `ykb_answer_records(identity_id, filter="wrong")` for wrong questions.
3. `ykb_chapters` → `ykb_chapter_questions` for question content; `ykb_question` for explanations.
4. `ykb_my_praises_all` / `ykb_my_comments_all` / `ykb_notes_all` for global lists. The official API has no global endpoints for these, so the server scans your touched questions with pacing and caches results; repeat calls resume where they left off (`remaining>0`), or use `ykb_sync` for bulk runs.
5. `ykb_search_local` to search the cache offline.

### Data & rate limiting

- Cache: `~/.ykb-mcp/cache.db` (SQLite). Override the directory with `YKB_MCP_HOME`.
- Every request is paced (~1.2–2 s/request; tune with `YKB_MCP_MIN_INTERVAL` / `YKB_MCP_JITTER`).
- Business code 309 = session expired (credentials cleared, re-login required); 203 = no permission for a chapter (VIP/purchase).

### Real-account smoke test (read-only)

```bash
uv run python -m ykb_mcp.smoke
```

Password is entered locally via getpass and never stored.

## Development

```bash
uv sync
uv run pytest
```

Tests cover the signature algorithm (pinned vector), DES decryption (pinned ciphertext vectors), header/credential injection, 309 handling, the cache layer, the local web login flow, and end-to-end tests of all MCP tools over a mock transport.

## License

[MIT](LICENSE)