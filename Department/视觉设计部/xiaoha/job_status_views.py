"""Synchronize and display Xiaoha background job state."""

from __future__ import annotations

from typing import Any


def _sync_background_jobs_legacy(
    *,
    calculate_finishing_progress,
    calculate_smooth_running_progress,
    clear_task_progress,
    format_user_facing_error_message,
    get_task_progress,
    get_task_runtime,
    record_background_job_error,
    st,
    store_completed_background_job_result,
    sys,
    time,
) -> None:
    runtime = get_task_runtime()
    jobs = st.session_state.get("background_jobs") or {}
    for feature_key, job_info in list(jobs.items()):
        if job_info.get("status") != "running":
            continue
        job_id = str(job_info.get("job_id") or "")
        if not job_id:
            continue
        with runtime.lock:
            future = runtime.futures.get(job_id)
        if future is None:
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                    waiting=bool(progress_info.get("request_waiting")),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            else:
                job_info["status"] = "error"
                job_info["error"] = "后台任务状态已丢失，请重新提交任务。"
                job_info["progress"] = 0
                job_info["stage"] = "任务状态丢失"
            continue
        if bool(job_info.get("completion_pending")):
            completion_started_at = float(job_info.get("completion_started_at") or time.time())
            completion_start_progress = int(
                job_info.get("completion_start_progress")
                or job_info.get("progress")
                or 1
            )
            animated_progress = calculate_finishing_progress(
                completion_start_progress,
                time.time() - completion_started_at,
            )
            job_info["progress"] = animated_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            if animated_progress < 100:
                continue
            try:
                result = future.result()
            except Exception as exc:
                progress_info = get_task_progress(job_id) or {}
                failed_stage = str(progress_info.get("stage") or "任务执行失败").strip()
                user_error = format_user_facing_error_message(exc)
                job_info["status"] = "error"
                job_info["error"] = (
                    f"{failed_stage}：{user_error}"
                    if failed_stage and failed_stage != "任务执行失败"
                    else user_error
                )
                job_info["progress"] = 0
                job_info["stage"] = failed_stage or "任务执行失败"
                record_background_job_error(job_id, feature_key, failed_stage, exc)
            else:
                store_completed_background_job_result(feature_key, job_info, result)
            with runtime.lock:
                runtime.futures.pop(job_id, None)
            clear_task_progress(job_id)
            continue
        if not future.done():
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                    waiting=bool(progress_info.get("request_waiting")),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            continue
        try:
            result = future.result()
        except Exception as exc:
            progress_info = get_task_progress(job_id) or {}
            failed_stage = str(progress_info.get("stage") or "任务执行失败").strip()
            user_error = format_user_facing_error_message(exc)
            job_info["status"] = "error"
            job_info["error"] = (
                f"{failed_stage}：{user_error}"
                if failed_stage and failed_stage != "任务执行失败"
                else user_error
            )
            job_info["progress"] = 0
            job_info["stage"] = failed_stage or "任务执行失败"
            print(
                f"[background-job] job_id={job_id} feature={feature_key} stage={failed_stage} "
                f"error={type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            record_background_job_error(job_id, feature_key, failed_stage, exc)
            with runtime.lock:
                runtime.futures.pop(job_id, None)
            clear_task_progress(job_id)
        else:
            completion_start_progress = calculate_smooth_running_progress(
                int(job_info.get("progress") or 1),
                100,
            )
            job_info["progress"] = completion_start_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            job_info["completion_pending"] = True
            job_info["completion_started_at"] = time.time()
            job_info["completion_start_progress"] = completion_start_progress


def record_background_job_error(
    job_id,
    feature_key,
    stage,
    exc,
    *,
    OPENROUTER_ERROR_LOG_FILE,
    _OPENROUTER_ERROR_LOG_LOCK,
    datetime,
    json,
    redact_background_error_text,
    sys,
    timezone,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": str(job_id or ""),
        "feature_key": str(feature_key or ""),
        "stage": redact_background_error_text(stage),
        "error_type": type(exc).__name__,
        "error": redact_background_error_text(exc),
    }
    try:
        OPENROUTER_ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with _OPENROUTER_ERROR_LOG_LOCK:
            with OPENROUTER_ERROR_LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(serialized + "\n")
        print(f"[image-task-error] {serialized}", file=sys.stderr)
    except Exception as log_exc:
        print(
            f"[background-job-log] write_failed={type(log_exc).__name__}: {log_exc}",
            file=sys.stderr,
        )


def get_session_background_job_records(*, st) -> list[dict[str, Any]]:
    records = [
        item
        for item in list(st.session_state.get("background_job_queue") or [])
        if isinstance(item, dict)
    ]
    seen_job_ids = {str(item.get("job_id") or "") for item in records}
    for feature_key, job_info in dict(st.session_state.get("background_jobs") or {}).items():
        if not isinstance(job_info, dict):
            continue
        job_id = str(job_info.get("job_id") or "")
        if not job_id or job_id in seen_job_ids:
            continue
        job_info.setdefault("feature_key", str(feature_key or ""))
        records.append(job_info)
        seen_job_ids.add(job_id)
    st.session_state.background_job_queue = records
    return records


def get_active_session_background_jobs(*, get_session_background_job_records) -> list[dict[str, Any]]:
    return [
        job_info
        for job_info in get_session_background_job_records()
        if str(job_info.get("status") or "").strip().lower() in {"queued", "running"}
    ]


def _mark_background_job_failed(
    runtime,
    job_info,
    feature_key,
    job_id,
    exc,
    *,
    clear_task_progress,
    format_user_facing_error_message,
    get_task_progress,
    record_background_job_error,
    sys,
) -> None:
    progress_info = get_task_progress(job_id) or {}
    failed_stage = str(progress_info.get("stage") or "任务执行失败").strip()
    user_error = format_user_facing_error_message(exc)
    job_info["status"] = "error"
    job_info["error"] = (
        f"{failed_stage}：{user_error}"
        if failed_stage and failed_stage != "任务执行失败"
        else user_error
    )
    job_info["progress"] = 0
    job_info["stage"] = failed_stage or "任务执行失败"
    print(
        f"[background-job] job_id={job_id} feature={feature_key} stage={failed_stage} "
        f"error={type(exc).__name__}: {exc}",
        file=sys.stderr,
    )
    record_background_job_error(job_id, feature_key, failed_stage, exc)
    runtime.release_generation_job(job_id)
    clear_task_progress(job_id)


def sync_background_jobs(
    *,
    Any,
    _mark_background_job_failed,
    calculate_finishing_progress,
    calculate_smooth_running_progress,
    clear_task_progress,
    get_session_background_job_records,
    get_task_progress,
    get_task_runtime,
    st,
    store_completed_background_job_result,
    time,
) -> None:
    runtime = get_task_runtime()
    jobs = get_session_background_job_records()
    for job_info in jobs:
        status = str(job_info.get("status") or "").strip().lower()
        if status not in {"queued", "running"}:
            continue
        feature_key = str(job_info.get("feature_key") or "").strip()
        job_id = str(job_info.get("job_id") or "")
        if not job_id:
            continue
        with runtime.lock:
            future = runtime.futures.get(job_id)
        if future is None:
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                    waiting=bool(progress_info.get("request_waiting")),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            else:
                job_info["status"] = "error"
                job_info["error"] = "后台任务状态已丢失，请重新提交任务。"
                job_info["progress"] = 0
                job_info["stage"] = "任务状态丢失"
            continue

        queue_state = runtime.get_generation_queue_state(job_id)
        if status == "queued" and queue_state.get("state") == "queued":
            ahead_count = max(int(queue_state.get("ahead_count") or 0), 0)
            job_info["queue_ahead"] = ahead_count
            job_info["queue_position"] = max(int(queue_state.get("queue_position") or 1), 1)
            job_info["progress"] = 1
            job_info["stage"] = (
                f"排队中，前面还有 {ahead_count} 个任务"
                if ahead_count
                else "排队中，即将开始"
            )
            continue
        if status == "queued":
            job_info["status"] = "running"
            job_info["queue_ahead"] = 0
            job_info["queue_position"] = 0
            job_info["stage"] = "排队结束，正在启动任务"

        if bool(job_info.get("completion_pending")):
            completion_started_at = float(job_info.get("completion_started_at") or time.time())
            completion_start_progress = int(
                job_info.get("completion_start_progress")
                or job_info.get("progress")
                or 1
            )
            animated_progress = calculate_finishing_progress(
                completion_start_progress,
                time.time() - completion_started_at,
            )
            job_info["progress"] = animated_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            if animated_progress < 100:
                continue
            try:
                result = future.result()
            except Exception as exc:
                _mark_background_job_failed(runtime, job_info, feature_key, job_id, exc)
            else:
                store_completed_background_job_result(feature_key, job_info, result)
                runtime.release_generation_job(job_id)
                clear_task_progress(job_id)
            continue

        if not future.done():
            progress_info = get_task_progress(job_id)
            if progress_info:
                job_info["progress"] = calculate_smooth_running_progress(
                    int(job_info.get("progress") or 1),
                    int(progress_info.get("percent") or 1),
                    waiting=bool(progress_info.get("request_waiting")),
                )
                job_info["stage"] = str(progress_info.get("stage") or job_info.get("stage") or "")
            continue
        try:
            future.result()
        except Exception as exc:
            _mark_background_job_failed(runtime, job_info, feature_key, job_id, exc)
        else:
            completion_start_progress = calculate_smooth_running_progress(
                int(job_info.get("progress") or 1),
                100,
            )
            job_info["progress"] = completion_start_progress
            job_info["stage"] = "结果已生成，正在完成最后处理"
            job_info["completion_pending"] = True
            job_info["completion_started_at"] = time.time()
            job_info["completion_start_progress"] = completion_start_progress

    latest_by_feature: dict[str, dict[str, Any]] = {}
    for job_info in jobs:
        feature_key = str(job_info.get("feature_key") or "").strip()
        if feature_key:
            latest_by_feature[feature_key] = job_info
    st.session_state.background_job_queue = jobs
    st.session_state.background_jobs = latest_by_feature
