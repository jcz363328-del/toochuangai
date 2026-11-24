"""Account-scoped persistent image conversations and their Streamlit view."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


CHAT_CSS = """<style>
/* Chat owns its viewport and controls; workbench form rules must not leak in. */
body:has(.qa-page-title) section[data-testid="stMain"] .block-container {
    max-width:none!important;padding:18px 24px 12px!important;
}
.qa-page-title {font-size:24px;font-weight:750;line-height:1.5;color:#f1f2ff;padding:0 0 12px;}
.qa-page-title span {font-size:11px;vertical-align:middle;padding:5px 10px;border:1px solid #393365;border-radius:20px;background:#191637;color:#c8baff;margin-left:10px;}
.st-key-qa_chat_layout {max-width:none!important;margin:0!important;width:100%;}
.st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {gap:0!important;align-items:stretch!important;}
.st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {flex:0 0 240px!important;width:240px!important;min-width:240px!important;}
.st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {flex:1!important;min-width:0!important;}
[data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_nav),[data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_main) {height:calc(100dvh - 112px)!important;flex:none!important;}
.st-key-qa_chat_nav,.st-key-qa_chat_main,.st-key-qa_chat_messages {flex:none!important;}
[data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_messages) {height:calc(100dvh - 312px)!important;flex:none!important;}
.st-key-qa_chat_nav {height:calc(100dvh - 112px)!important;min-height:560px;position:relative;background:#0b1126;border:0;border-right:1px solid #292d4c;border-radius:0;padding:20px 16px 64px!important;overflow:auto;gap:12px!important;}
.qa-brand {font-size:25px;color:#f3f0ff;margin-bottom:20px;line-height:1.5;}
.qa-brand:first-letter {color:#bda5ff;}
.st-key-qa_chat_nav > [data-testid="stElementContainer"]:has(.qa-nav-account) {position:absolute!important;bottom:16px;left:16px;right:16px;width:auto;}
.qa-nav-account {border-top:1px solid #282d4b;padding-top:18px;color:#cbd0e4;font-size:13px;}
.st-key-qa_chat_nav button {justify-content:flex-start!important;border:1px solid transparent!important;border-radius:10px!important;min-height:42px!important;box-shadow:none!important;}
.st-key-qa_chat_nav button p {font-size:14px!important;}
.st-key-qa_new_chat button {justify-content:center!important;background:#7046f6!important;margin-bottom:12px!important;}
.st-key-qa_chat_main {height:calc(100dvh - 112px)!important;min-height:560px;padding:12px 32px 0!important;gap:12px!important;transform:translateZ(0);}
.st-key-qa_chat_messages {height:calc(100dvh - 312px)!important;min-height:350px!important;max-width:960px!important;width:100%;margin:0 auto!important;overflow-x:hidden!important;border:0!important;padding:12px 8px!important;}
.st-key-qa_chat_messages [data-testid="stChatMessage"] {background:transparent!important;border:0;padding:16px 8px!important;}
.st-key-qa_chat_messages [data-testid="stChatMessage"] p {color:#e5e8f5!important;font-size:14px!important;line-height:1.75!important;}
.st-key-qa_chat_messages [data-testid="stCaptionContainer"] p {font-size:11px!important;color:#8c99bc!important;}
.st-key-qa_chat_messages [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {flex-direction:row-reverse;justify-content:flex-start!important;gap:16px;}
.st-key-qa_chat_messages [aria-label="Chat message from user"] {background:#202344;border:1px solid #3c3b69;border-radius:16px;padding:14px 20px;max-width:82%;width:fit-content!important;flex:0 1 auto!important;min-width:0!important;margin:0!important;}
.st-key-qa_chat_messages [data-testid="stChatMessageAvatarUser"] {background:#303354!important;color:#cfd3f4!important;}
.st-key-qa_chat_messages button {background:transparent!important;color:#c9d1ed!important;border:1px solid #303652!important;border-radius:9px!important;box-shadow:none!important;}
.st-key-qa_chat_messages [data-testid="stLayoutWrapper"]:has(> [class*="st-key-qa_images_"]) {max-width:560px!important;}
.qa-welcome {text-align:center;padding:clamp(60px,13vh,160px) 20px 20px;}
.qa-welcome-icon {font-size:40px;color:#b39aff;line-height:1.4;}
.qa-welcome h2 {font-size:27px!important;line-height:1.6!important;color:#f1efff;margin:12px 0 6px!important;padding:0!important;}
.qa-welcome p {font-size:14px!important;line-height:1.8;color:#919bb9!important;}
.st-key-qa_chat_composer {position:fixed;bottom:4px;left:50%;transform:translateX(-50%);z-index:40;background:linear-gradient(145deg,#121c31,#10172a);border:1px solid #39415d!important;border-radius:22px;padding:14px 18px 10px!important;max-width:880px!important;width:calc(100% - 64px)!important;margin:0!important;gap:6px!important;box-shadow:0 16px 48px #02071660;transition:border-color .18s,box-shadow .18s;}
.st-key-qa_chat_composer:focus-within {border-color:#7963bb!important;box-shadow:0 0 0 3px #8b6aff0a,0 16px 48px #02071660;}
.st-key-qa_chat_composer > :is([data-testid="stLayoutWrapper"],[data-testid="stElementContainer"]) {flex:none!important;}
body:has(.qa-page-title) .st-key-qa_chat_composer [data-testid="stChatInput"] {border:0!important;border-radius:10px!important;background:transparent!important;min-height:60px!important;box-shadow:none!important;}
body:has(.qa-page-title) .st-key-qa_chat_composer [data-testid="stChatInput"] div {background:transparent!important;border-color:transparent!important;box-shadow:none!important;color:#c4cce3!important;}
.st-key-qa_chat_composer [data-testid="stChatInput"] :is(span,small) {color:#aab6d1!important;}
body:has(.qa-page-title) .st-key-qa_chat_composer [data-baseweb="textarea"] {border:0!important;box-shadow:none!important;background:transparent!important;}
body:has(.qa-page-title) .st-key-qa_chat_composer textarea {min-height:44px!important;height:44px!important;max-height:140px!important;resize:none!important;background:transparent!important;color:#e4e7f6!important;font-size:15px!important;line-height:1.6!important;padding:8px!important;}
body:has(.qa-page-title) .st-key-qa_chat_composer textarea::placeholder {color:#9da9c5!important;opacity:1!important;}
.st-key-qa_chat_composer [data-testid="stChatInputFileUploadButton"] button {color:#b9c2df!important;border:1px solid #39415d!important;border-radius:50%!important;width:32px;height:32px;}
.st-key-qa_chat_composer [data-testid="stChatInputSubmitButton"] {background:linear-gradient(135deg,#926bff,#7046f6)!important;color:white!important;border-radius:12px!important;width:38px;height:38px;box-shadow:0 4px 14px #7046f630!important;}
.st-key-qa_chat_composer [data-testid="stChatInputSubmitButton"]:disabled {background:#37304f!important;}
.st-key-qa_chat_composer [data-testid="stHorizontalBlock"] {max-width:340px;gap:8px!important;}
.st-key-qa_chat_composer [data-baseweb="select"] > div {min-height:30px!important;font-size:12px!important;border-radius:16px!important;background:#1b253c!important;border-color:#303a52!important;}
.st-key-qa_chat_composer [data-testid="stCaptionContainer"] p {font-size:11px!important;line-height:1.7!important;color:#7f8ca9!important;margin:0!important;padding-left:4px;}
.st-key-qa_chat_composer [data-testid="stChatInputInstructions"] {display:none!important;}
@media(max-width:800px){
 .st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {flex:0 0 170px!important;width:170px!important;min-width:170px!important;}
 .st-key-qa_chat_main {padding:8px 12px 0!important;}
 .st-key-qa_chat_composer {width:calc(100% - 24px)!important;}
 .qa-welcome h2 {font-size:22px!important;}
}
@media(max-width:540px){
 .st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {flex-direction:column!important;}
 .st-key-qa_chat_layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {width:100%!important;flex:auto!important;}
 .st-key-qa_chat_nav {height:150px!important;min-height:150px!important;padding:10px!important;}
 [data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_nav) {height:150px!important;}
 [data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_main) {height:auto!important;}
 [data-testid="stLayoutWrapper"]:has(> .st-key-qa_chat_messages) {height:45dvh!important;min-height:240px!important;}
 .qa-brand,.qa-nav-account {display:none;}
 .st-key-qa_chat_messages {height:45dvh!important;min-height:240px!important;}
 .st-key-qa_chat_main {height:auto!important;min-height:0;transform:none;}
 .st-key-qa_chat_composer {left:50%;width:calc(100% - 32px)!important;bottom:12px;}
}
</style>"""


class ChatStore:
    def __init__(self, root):
        self.root = Path(root) / "qa_conversations"
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, account TEXT NOT NULL, title TEXT NOT NULL,
                    updated TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY, chat TEXT NOT NULL, prompt TEXT NOT NULL,
                    refs TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
                    images TEXT DEFAULT '[]', error TEXT DEFAULT '', job TEXT DEFAULT '',
                    count INTEGER DEFAULT 1, ratio TEXT DEFAULT '',
                    created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS chats_account ON chats(account, updated);
                CREATE INDEX IF NOT EXISTS turns_chat_status ON turns(chat, status);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "conversations.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=NORMAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, account):
        chat = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO chats(id,account,title) VALUES(?,?,?)", (chat, account, "新对话"))
        return chat

    def list(self, account):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM chats WHERE account=? ORDER BY updated DESC,rowid DESC", (account,))]

    def turns(self, account, chat):
        with self.connect() as db:
            rows = db.execute("SELECT t.*, (strftime('%s','now') - strftime('%s',t.created)) AS age_seconds "
                              "FROM turns t JOIN chats c ON c.id=t.chat "
                              "WHERE c.account=? AND c.id=? ORDER BY t.rowid", (account, chat)).fetchall()
        return [dict(r, refs=json.loads(r["refs"]), images=json.loads(r["images"])) for r in rows]

    def add(self, account, chat, prompt, refs, model, count=1, ratio="", job=""):
        turn = uuid4().hex
        with self.connect() as db:
            # Serialize the read/check/insert across Streamlit sessions and
            # processes. A deferred transaction permits duplicate active turns.
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM chats WHERE account=? AND id=?", (account, chat)).fetchone():
                raise ValueError("无法访问此对话")
            if db.execute("SELECT 1 FROM turns WHERE chat=? AND status IN ('queued','running')", (chat,)).fetchone():
                raise ValueError("请等待当前图片生成完成")
            db.execute("INSERT INTO turns(id,chat,prompt,refs,model,status,count,ratio,job) VALUES(?,?,?,?,?,'queued',?,?,?)",
                       (turn, chat, prompt, json.dumps(refs), model, count, ratio, job))
            db.execute("UPDATE chats SET title=CASE WHEN title='新对话' THEN ? ELSE title END, "
                       "updated=CURRENT_TIMESTAMP WHERE id=?", (prompt[:24], chat))
        return turn

    def update(self, account, turn, *, status=None, images=None, error=None, job=None, only_active=False):
        values = {k: v for k, v in dict(status=status, images=images, error=error, job=job).items() if v is not None}
        if "images" in values:
            values["images"] = json.dumps(values["images"])
        if not values:
            return
        with self.connect() as db:
            db.execute("UPDATE turns SET " + ",".join(f"{k}=?" for k in values) +
                       " WHERE id=? AND chat IN (SELECT id FROM chats WHERE account=?)" +
                       (" AND status IN ('queued','running')" if only_active else ""),
                       [*values.values(), turn, account])

    def save_image(self, site, account, source):
        data, mime = site.load_image_bytes_from_url(source)
        suffix = ".jpg" if mime == "image/jpeg" else ".webp" if mime == "image/webp" else ".png"
        folder = self.root / hashlib.sha256(account.encode()).hexdigest()
        folder.mkdir(exist_ok=True)
        path = folder / (hashlib.sha256(data).hexdigest() + suffix)
        if not path.exists():
            # Concurrent turns can save the same content; readers must never
            # observe a partially written image.
            temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(data)
                try:
                    temporary.replace(path)
                except PermissionError:
                    # Windows can reject replacement when another writer has
                    # just published the same content-addressed file.
                    if not path.exists() or path.read_bytes() != data:
                        raise
            finally:
                temporary.unlink(missing_ok=True)
        return str(path)


def build_context(turns, prompt, new_refs):
    """An explicit new reference replaces the previous image; text follow-ups edit it."""
    previous = next((t for t in reversed(turns) if t["status"] == "completed" and t["images"]), None)
    refs = list(new_refs)
    if not refs and previous:
        refs = previous["images"][:1]
    history = "\n".join("用户：" + t["prompt"][:2000] for t in turns[-8:] if t["status"] == "completed")
    notes = "本轮上传了新的参考图，以本轮参考图为准。" if new_refs else (
        "第1张参考图是上一轮生成结果，请在它的基础上继续修改，保持未要求修改的内容。" if previous else "请根据文字要求生成图片。")
    return refs, f"{notes}\n以下是此前的用户要求，仅供理解上下文：\n{history}\n本轮最新要求（优先执行）：\n{prompt}"


def run_chat_job(site, context, runner):
    store = ChatStore(context["qa_chat_root"])
    account, turn = context["account_name"], context["qa_turn_id"]
    store.update(account, turn, status="running", job=context.get("job_id", ""))
    try:
        result = runner(context)
        sources = list(result.get("images") or [])
        if not sources:
            raise RuntimeError("模型未返回图片，请重试或调整要求。")
        images = [store.save_image(site, account, source) for source in sources]
        store.update(account, turn, status="completed", images=images)
        return result
    except Exception as exc:
        store.update(account, turn, status="error", error=str(exc))
        raise


def submit_turn(site, store, account, chat, prompt, references, model, count, ratio, prior_turns=None):
    turns = store.turns(account, chat) if prior_turns is None else prior_turns
    refs, request = build_context(turns, prompt, references)
    # Read references before creating a queued record, so a missing image cannot
    # leave the conversation permanently busy.
    inputs = [site.image_url_as_uploaded_input(source, f"reference_{i}.png") for i, source in enumerate(refs)]
    job_id = "ai_qa_image_" + uuid4().hex
    turn = store.add(account, chat, prompt, references, model, count, ratio, job=job_id)
    try:
        feature = dict(site.get_feature_by_key("ai_qa_image"))
        feature["max_output_images"] = count
        job = site.submit_feature_job(feature, {
            "feature": feature, "model": model,
            "prompt": site.build_prompt(feature, request, ratio, "只生成图片，严格执行本轮要求。"),
            "custom_prompt": prompt, "uploaded_files": inputs,
            "output_mode": "image", "max_output_images": count,
            "account_name": account, "aspect_ratio": ratio,
            "qa_chat_root": str(store.root.parent), "qa_turn_id": turn, "job_id": job_id,
        })
        store.update(account, turn, job=job["job_id"])
        return turn
    except Exception as exc:
        store.update(account, turn, status="error", error=str(exc))
        raise


def refresh_turn_status(site, store, account, chat, turn):
    """Recover a terminal worker state without inventing generation progress."""
    if turn["status"] not in {"queued", "running"}:
        return turn, {}
    runtime = site.get_task_runtime()
    state = runtime.get_generation_queue_state(turn["job"])
    if state["state"] in {"missing", "completed", "canceled"}:
        # A worker can persist its result between the page read and this lookup.
        latest = next((item for item in store.turns(account, chat) if item["id"] == turn["id"]), turn)
        if latest["status"] not in {"queued", "running"}:
            return latest, state
        error = ""
        if state["state"] == "canceled":
            error = "任务在排队时已取消，未向图片服务提交。"
        elif state["state"] == "completed":
            with runtime.lock:
                future = runtime.futures.get(turn["job"])
            if future is not None:
                failure = future.exception()
                if failure is not None:
                    error = str(failure)
        elif int(latest.get("age_seconds") or 0) >= 60:
            # Allow the short DB-commit / queue-submit gap. After a restart the
            # remote synchronous request may still exist and must not be retried.
            error = "服务重启或任务状态已丢失，远端结果尚未确认。系统未自动重新提交，请先核实原任务结果，避免重复计费。"
        if error:
            store.update(account, turn["id"], status="error", error=error, only_active=True)
            latest = next((item for item in store.turns(account, chat) if item["id"] == turn["id"]), latest)
        return latest, state
    return turn, state


def render(site, feature, default_model, ratio):
    st = site.st
    account = str(st.session_state.get("auth_username") or "admin")
    store = ChatStore(site.HISTORY_DIR)
    active_key = "qa_chat_active_" + hashlib.sha256(account.encode()).hexdigest()[:16]
    st.markdown(CHAT_CSS, unsafe_allow_html=True)
    title, history = st.columns([6, 1], vertical_alignment="center")
    with title:
        st.markdown('<div class="qa-page-title">AI问答生图 <span>AI 增强</span></div>', unsafe_allow_html=True)
    with history:
        if st.button("历史图片", icon=":material/history:", key="qa_legacy_history", use_container_width=True):
            site.render_fusion_history_dialog(feature)
    with st.container(key="qa_chat_layout"):
        nav, main = st.columns([1, 4], gap="large")
        with nav, st.container(key="qa_chat_nav"):
            st.markdown('<div class="qa-brand">✦ <b>小哈</b></div>', unsafe_allow_html=True)
            if st.button("＋ 新建对话", key="qa_new_chat", use_container_width=True, type="primary"):
                st.session_state[active_key] = store.create(account)
                st.rerun()
            st.caption("最近对话")
            chats = store.list(account)
            if st.session_state.get(active_key) not in {c["id"] for c in chats}:
                st.session_state[active_key] = chats[0]["id"] if chats else store.create(account)
                chats = store.list(account)
            chat = st.session_state[active_key]
            for item in chats:
                if st.button(item["title"], key="qa_open_" + item["id"], use_container_width=True,
                             type="secondary"):
                    st.session_state[active_key] = item["id"]
                    st.rerun()
            st.markdown(f'<div class="qa-nav-account">◉ &nbsp; {site.html.escape(account)}</div>', unsafe_allow_html=True)
            st.markdown(f'<style>.st-key-qa_open_{chat} button {{background:#26224f!important;border-color:#39336a!important;}}</style>', unsafe_allow_html=True)
        with main, st.container(key="qa_chat_main"):
            render_conversation(site, store, account, chat, default_model, ratio)


def render_conversation(site, store, account, chat, default_model, ratio):
    st = site.st

    @st.fragment(run_every="2s")
    def conversation():
        turns = store.turns(account, chat)
        busy = False
        with st.container(key="qa_chat_messages", height=520, border=False):
            if not turns:
                st.markdown('<div class="qa-welcome"><div class="qa-welcome-icon">✦</div>'
                            '<h2>今天想创作什么图片？</h2>'
                            '<p>描述你的灵感，或上传参考图，让小哈帮你实现。</p>'
                            '</div>', unsafe_allow_html=True)
            for index, turn in enumerate(turns):
                turn, queue_state = refresh_turn_status(site, store, account, chat, turn)
                turns[index] = turn
                with st.chat_message("user"):
                    if turn["refs"]:
                        st.image(turn["refs"], width=100)
                    st.write(turn["prompt"])
                with st.chat_message("assistant", avatar="✨"):
                    status = turn["status"]
                    if status in {"queued", "running"}:
                        busy = True
                        if queue_state.get("state") == "running":
                            progress = site.get_task_progress(turn["job"]) or {}
                            st.status(str(progress.get("stage") or "正在生成图片…"), state="running")
                        else:
                            ahead = int(queue_state.get("ahead_count") or 0)
                            st.info(f"排队中，当前账号前面还有 {ahead} 个任务。" if ahead else "排队中，等待可用生成名额。")
                    elif status == "error":
                        st.error(site.format_user_facing_error_message(turn["error"] or "生成失败，请重试"))
                    else:
                        st.write("已为你生成图片，可以继续输入要求修改。")
                        with st.container(key="qa_images_" + turn["id"]):
                            site.render_zoomable_image_gallery(
                                turn["images"], columns=min(len(turn["images"]), 2), thumb_height=300,
                                component_key="qa_result_" + turn["id"], include_full_src=True,
                                full_images=[site.normalize_history_image_source(p) for p in turn["images"]],
                            )
                        for i, source in enumerate(turn["images"]):
                            path = Path(source)
                            st.download_button(f"下载原图 {i + 1}", data=lambda p=path: p.read_bytes(),
                                               file_name=path.name, key=f"qa_dl_{turn['id']}_{i}")
                    st.caption(turn["model"])
                    retry_model = turn["model"]
                    if status == "error":
                        retry_options = list(dict.fromkeys([turn["model"], *site.MODEL_OPTIONS]))
                        retry_model = st.selectbox("重试模型", retry_options, key="qa_retry_model_" + turn["id"],
                                                   format_func=site.get_model_display_name,
                                                   disabled=any(t["status"] in {"queued", "running"} for t in turns))
                    if status in {"completed", "error"} and st.button("重新生成", key="qa_retry_" + turn["id"], disabled=any(
                            t["status"] in {"queued", "running"} for t in turns)):
                        try:
                            # Replay exactly this turn's original inputs, not the latest output.
                            prior = turns[:turns.index(turn)]
                            submit_turn(site, store, account, chat, turn["prompt"], turn["refs"], retry_model,
                                        turn["count"], turn["ratio"] or ratio, prior_turns=prior)
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

        with st.container(key="qa_chat_composer"):
            input_slot = st.container()
            controls = st.columns([2.4, 1])
            options = list(site.MODEL_OPTIONS)
            with controls[0]:
                model = st.selectbox("模型", options, index=options.index(default_model) if default_model in options else 0,
                                     key="qa_model_" + chat, disabled=busy, label_visibility="collapsed",
                                     format_func=lambda name: "Nano Banana 2.1" if "nano-banana-2.1" in name else name)
            with controls[1]:
                count = st.selectbox("生成张数", [1, 2, 3, 4], key="qa_count_" + chat, disabled=busy,
                                     label_visibility="collapsed", format_func=lambda n: f"{n} 张")
            with input_slot:
                message = st.chat_input("描述画面，或继续修改上一张图片…", key="qa_input_" + chat,
                                        accept_file="multiple", file_type=["png", "jpg", "jpeg", "webp"], disabled=busy)
            if message:
                prompt = message if isinstance(message, str) else message.text
                uploads = [] if isinstance(message, str) else message.files
                if not prompt.strip():
                    st.warning("请输入图片要求")
                elif len(uploads) > 3:
                    st.warning("最多上传 3 张参考图")
                else:
                    try:
                        refs = [store.save_image(site, account, site.uploaded_input_to_data_url(f)) for f in uploads]
                        submit_turn(site, store, account, chat, prompt.strip(), refs, model, count, ratio)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    conversation()
