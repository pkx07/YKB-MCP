# 医考帮接口协议要点

本项目维护者整理的接口协议笔记，供开发维护参考。

## 网关与请求头

- 网关：`https://api.yikaobang.com.cn/index.php` + 路径
- 伪装安卓客户端：
  - `User-Agent: Redmi_23078RKD5C`
  - `client-type: android`、`app-type: ykb`、`app-version: 2801`
  - `uuid: 4f07ccb6e858592c`、`channel: 10000`
  - `timestamp`: 秒级时间戳
  - `signature`: 见下
- POST 为 `application/x-www-form-urlencoded`；GET 参数放 query。

## 签名

```
paramStr  = 所有参数按 key 升序拼接 "k=v"（无分隔符）
build     = paramStr + app_id + timestamp
md5hex    = md5(build)
signature = sha1(md5hex + "bfde83c3208f4bfe97a57765ee824e92")
```

签名在注入登录参数（token/secret/user_id）与默认 app_id 之后计算。

## 登录与会话

- `POST /User/Main/login`：`mobile` + `password=md5(明文密码)` + `beta_version=0` + `app_id=1`
- 返回 `data.token / data.secret / data.user_id`（另有 user_uuid、nickname 等），此后每个请求参数都注入这三项。
- 业务码：`200` 成功；`309` 会话过期（清凭据重新登录）；`203` 无查看权限（VIP/题库未购买，勿重试）。

## 题目数据解密

`allquestion/question/list`、`allquestion/question/info` 等接口的 `data` 为 Base64(DES/CBC/PKCS5Padding)：

- 密钥：`de158b8749e6a2d0` 的前 8 字节，即 `de158b87`（Java DESKeySpec 行为）
- IV：`0x12 34 56 78 90 AB CD EF`
- 解密后为 JSON（如 `{"list":[...]}`）。

## 主要读接口

| 接口 | 方法 | 关键参数 | 说明 |
|---|---|---|---|
| `/allQuestion/question/subjectV2` | GET | user_id | 身份树；identity_id=0/空 为分组节点需展开 |
| `/allquestion/question/chapter` | POST | identity_id, category=chapter, type=all, search_where=[], module_type, app_id, am_pm | 科目/章节目录（叶子含 count/updated_at） |
| `/allquestion/question/list` | POST | identity_id, primary_id=chapter_id, category=chapter, type=all, module_type, am_pm, app_id | 整章题目（DES 加密），题目含 is_collection_question/cut_question/user_answer |
| `/allquestion/main/userAnswer` | GET | app_id, module_type=1, identity_id=叶子身份, category=chapter, type=all, is_vip=0, is_svip=0 | 做题记录：question_id/answer/is_right/cut_question/update_time/duration |
| `/comment/main/hot` | POST | subject_id, obj_id=question_id, identity_id=外层身份(通常=subject_id), type(''/'recommend'/'replies'/'newst'), comment_type=2, break_point=ts, page, app_id | 热门评论，data.hot + data.time_line |
| `/Comment/Main/list` | POST | 同上 + func=mypraise\|mycomment | 某题下我的点赞/我的评论 |
| `/allQuestion/Note/getNote` | GET | question_id, subject_id, identity_id, app_id, module_type=1, page, size | 我的笔记（content/ctime/img[b_img,s_img]） |

做题记录按「叶子身份」返回：如临床期末根身份 20101 直接查为 0 条，真实记录挂在 201010~201013 等叶子下，需先展开身份树。临床期末 app_id=40，缺省兜底 12/40 视题库而定。

## 写接口（本项目仅实现三个）

| 接口 | 关键参数 |
|---|---|
| `/Comment/Main/praise` | id=comment_id, obj_id, type=1, comment_type=2, subject_id, identity_id, app_id |
| `/Comment/Main/publish` | obj_id, content, comment_type=2, subject_id, identity_id, app_id |
| `/allQuestion/cutQuestion/cut` | question_id, operate=add\|del, chapter_id, subject_id, identity_id, unit_id='', app_id |

其余已知写接口（未实现）：`/Question/Answer/postBatchForAll`（作答上传）、`/allquestion/main/redoAnswerWithWrong`（章节重做）、`/allQuestion/Note/pushNote` / `cleanNote` / `uploads`（笔记增删/图片上传）。

## 风控注意

- 批量请求应带随机抖动（请求间隔约 1.2~3.2s）模拟真人刷题节奏；本项目默认 1.2s + 0~0.8s 抖动。
- 无全局「收藏/我的评论/我的点赞/笔记」列表接口，只能按题拉取归纳；本项目以已做题集合 + 限速扫描 + SQLite 缓存实现，断点续传。