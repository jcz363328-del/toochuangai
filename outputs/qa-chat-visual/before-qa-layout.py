"""Account-scoped persistent image conversations and their Streamlit view."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class ChatStore:
    def __init__(self, root):
        self.root = Path(root) / "qa_conversations"
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
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
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "conversations.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
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
            rows = db.execute("SELECT t.* FROM turns t JOIN chats c ON c.id=t.chat "
                              "WHERE c.account=? AND c.id=? ORDER BY t.rowid", (account, chat)).fetchall()
        return [dict(r, refs=json.loads(r["refs"]), images=json.loads(r["images"])) for r in rows]

    def add(self, account, chat, prompt, refs, model, count=1, ratio=""):
        turn = uuid4().hex
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM chats WHERE account=? AND id=?", (account, chat)).fetchone():
                raise ValueError("无法访问此对话")
            if db.execute("SELECT 1 FROM turns WHERE chat=? AND status IN ('queued','running')", (chat,)).fetchone():
                raise ValueError("请等待当前图片生成完成")
            db.execute("INSERT INTO turns(id,chat,prompt,refs,model,status,count,ratio) VALUES(?,?,?,?,?,'queued',?,?)",
                       (turn, chat, prompt, json.dumps(refs), model, count, ratio))
            db.execute("UPDATE chats SET title=CASE WHEN title='新对话' THEN ? ELSE title END, "
                       "updated=CURRENT_TIMESTAMP WHERE id=?", (prompt[:24], chat))
        return turn

    def update(self, account, turn, *, status=None, images=None, error=None, job=None):
        values = {k: v for k, v in dict(status=status, images=images, error=error, job=job).items() if v is not None}
        if "images" in values:
            values["images"] = json.dumps(values["images"])
        if not values:
            return
        with self.connect() as db:
            db.execute("UPDATE turns SET " + ",".join(f"{k}=?" for k in values) +
                       " WHERE id=? AND chat IN (SELECT id FROM chats WHERE account=?)",
                       [*values.values(), turn, account])

    def save_image(self, site, account, source):
        data, mime = site.load_image_bytes_from_url(source)
        suffix = ".jpg" if mime == "image/jpeg" else ".webp" if mime == "image/webp" else ".png"
        folder = self.root / hashlib.sha256(account.encode()).hexdigest()
        folder.mkdir(exist_ok=True)
        path = folder / (hashlib.sha256(data).hexdigest() + suffix)
        if not path.exists():
            path.write_bytes(data)
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
    turn = store.add(account, chat, prompt, references, model, count, ratio)
    try:
        feature = dict(site.get_feature_by_key("ai_qa_image"))
        feature["max_output_images"] = count
        job = site.submit_feature_job(feature, {
            "feature": feature, "model": model,
            "prompt": site.build_prompt(feature, request, ratio, "只生成图片，严格执行本轮要求。"),
            "custom_prompt": prompt, "uploaded_files": inputs,
            "output_mode": "image", "max_output_images": count,
            "account_name": account, "aspect_ratio": ratio,
            "qa_chat_root": str(store.root.parent), "qa_turn_id": turn,
        })
        store.update(account, turn, job=job["job_id"])
        return turn
    except Exception as exc:
        store.update(account, turn, status="error", error=str(exc))
        raise


def render(site, feature, default_model, ratio):
    st = site.st
    account = str(st.session_state.get("auth_username") or "admin")
    store = ChatStore(site.HISTORY_DIR)
    active_key = "qa_chat_active_" + hashlib.sha256(account.encode()).hexdigest()[:16]
    st.markdown("""<style>
    .st-key-qa_chat_layout {max-width:1500px;margin:0 auto;}
    .st-key-qa_chat_nav {background:#0d1429;border:1px solid #293253;border-radius:14px;padding:16px;}
    .st-key-qa_chat_composer {background:#101a31;border:1px solid #6259a6;border-radius:16px;padding:16px;}
    .st-key-qa_chat_composer textarea {min-height:100px!important;}
    .st-key-qa_chat_messages [data-testid="stChatMessage"] {background:transparent;border:0;}
    .st-key-qa_chat_messages {min-height:260px;}
    </style>""", unsafe_allow_html=True)
    site.render_image_workbench_header(feature)
    with st.container(key="qa_chat_layout"):
        nav, main = st.columns([1, 4], gap="large")
        with nav, st.container(key="qa_chat_nav"):
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
                             type="primary" if item["id"] == chat else "secondary"):
                    st.session_state[active_key] = item["id"]
                    st.rerun()
        with main:
            render_conversation(site, store, account, chat, default_model, ratio)


def render_conversation(site, store, account, chat, default_model, ratio):
    st = site.st

    @st.fragment(run_every="2s")
    def conversation():
        turns = store.turns(account, chat)
        busy = False
        with st.container(key="qa_chat_messages", height=520, border=False):
            if not turns:
                st.markdown("### 今天想创作什么图片？")
                st.caption("描述画面或上传参考图，生成后可以继续对话修改。")
            for turn in turns:
                with st.chat_message("user"):
                    if turn["refs"]:
                        st.image(turn["refs"], width=100)
                    st.write(turn["prompt"])
                with st.chat_message("assistant", avatar="✨"):
                    status = turn["status"]
                    if status in {"queued", "running"}:
                        runtime = site.get_task_runtime()
                        with runtime.lock:
                            known = turn["job"] in runtime.futures
                        if turn["job"] and not known:
                            store.update(account, turn["id"], status="error", error="服务已重启，任务中断，请重新生成。")
                            st.rerun()
                        busy = True
                        progress = site.get_task_progress(turn["job"]) or {}
                        st.status(str(progress.get("stage") or "已提交，正在排队生成…"), state="running")
                    elif status == "error":
                        st.error(turn["error"] or "生成失败，请重试")
                    else:
                        st.write("已为你生成图片，可以继续输入要求修改。")
                        site.render_zoomable_image_gallery(
                            turn["images"], columns=min(len(turn["images"]), 2), thumb_height=340,
                            component_key="qa_result_" + turn["id"], include_full_src=True,
                            full_images=[site.normalize_history_image_source(p) for p in turn["images"]],
                        )
                        for i, source in enumerate(turn["images"]):
                            path = Path(source)
                            st.download_button(f"下载原图 {i + 1}", data=lambda p=path: p.read_bytes(),
                                               file_name=path.name, key=f"qa_dl_{turn['id']}_{i}")
                    st.caption(turn["model"])
                    if status in {"completed", "error"} and st.button("重新生成", key="qa_retry_" + turn["id"], disabled=any(
                            t["status"] in {"queued", "running"} for t in turns)):
                        try:
                            # Replay exactly this turn's original inputs, not the latest output.
                            prior = turns[:turns.index(turn)]
                            submit_turn(site, store, account, chat, turn["prompt"], turn["refs"], turn["model"],
                                        turn["count"], turn["ratio"] or ratio, prior_turns=prior)
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

        with st.container(key="qa_chat_composer"):
            controls = st.columns([3, 1])
            options = list(site.MODEL_OPTIONS)
            with controls[0]:
                model = st.selectbox("模型", options, index=options.index(default_model) if default_model in options else 0,
                                     key="qa_model_" + chat, disabled=busy)
            with controls[1]:
                count = st.selectbox("生成张数", [1, 2, 3, 4], key="qa_count_" + chat, disabled=busy)
            message = st.chat_input("描述画面，或继续修改上一张图片…", key="qa_input_" + chat,
                                    accept_file="multiple", file_type=["png", "jpg", "jpeg", "webp"], disabled=busy, max_chars=12000)
            st.caption("＋ 上传参考图（最多 3 张） · Enter 发送，Shift + Enter 换行 · 不上传时继续修改上一张结果")
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
