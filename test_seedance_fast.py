import json
import argparse
import sys
import time
import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config


def pick_value(data, keys):
    for key in keys:
        if key in data and data[key]:
            return data[key]
    return None


def post_with_fallback(base_url, headers, payload):
    paths = [
        "/contents/generations/tasks",
        "/content/generations/tasks",
        "/content_generation/tasks",
        "/content-generation/tasks",
    ]
    tried = []
    for path in paths:
        url = f"{base_url}{path}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
        except Exception as exc:
            tried.append({"url": url, "error": str(exc)})
            continue
        tried.append({"url": url, "status_code": response.status_code})
        if response.status_code != 404:
            return response, path, tried
    return None, None, tried


def get_with_fallback(base_url, task_id, headers):
    paths = [
        f"/contents/generations/tasks/{task_id}",
        f"/content/generations/tasks/{task_id}",
        f"/content_generation/tasks/{task_id}",
        f"/content-generation/tasks/{task_id}",
    ]
    tried = []
    for path in paths:
        url = f"{base_url}{path}"
        try:
            response = requests.get(url, headers=headers, timeout=60)
        except Exception as exc:
            tried.append({"url": url, "error": str(exc)})
            continue
        tried.append({"url": url, "status_code": response.status_code})
        if response.status_code != 404:
            return response, path, tried
    return None, None, tried


def extract_task_id(data):
    task_id = pick_value(data, ["id", "task_id"])
    if task_id:
        return task_id
    for key in ["data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["id", "task_id"])
            if nested:
                return nested
    return None


def extract_status(data):
    direct = pick_value(data, ["status", "state", "task_status"])
    if direct:
        return str(direct).lower()
    for key in ["data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["status", "state", "task_status"])
            if nested:
                return str(nested).lower()
    return "unknown"


def extract_video_url(data):
    direct = pick_value(data, ["video_url"])
    if direct:
        return direct
    for key in ["content", "data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["video_url"])
            if nested:
                return nested
    return None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        action="append",
        help="可重复传入多次 --prompt 以并行生成多条视频",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="当只传入一个 prompt 时，按数量批量生成",
    )
    parser.add_argument(
        "--image-path",
        action="append",
        help="本地图片路径，可重复传入多次",
    )
    parser.add_argument(
        "--video-path",
        action="append",
        help="本地视频路径或视频 URL，可重复传入多次",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
    )
    parser.add_argument(
        "--result-json",
        default="seedance_result.json",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--max-download-workers",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--max-task-workers",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        help="期望视频时长（秒）",
    )
    return parser.parse_args()


def build_media_url(media_path, default_mime, label, allow_local_file=True):
    if str(media_path).startswith(("http://", "https://")):
        return str(media_path)
    if not allow_local_file:
        raise ValueError(f"{label}仅支持 http/https 链接，请先上传到可访问 URL: {media_path}")
    path = Path(media_path)
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"{label}路径是目录，请传具体文件路径: {media_path}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label}不存在: {media_path}")
    mime_type = mimetypes.guess_type(str(path))[0] or default_mime
    media_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{media_base64}"


def build_content(prompt, image_path, video_path):
    content = [{"type": "text", "text": prompt}]
    if image_path:
        image_paths = image_path if isinstance(image_path, (list, tuple)) else [image_path]
        image_role = "reference_image" if video_path else None
        for path in image_paths:
            image_item = {
                "type": "image_url",
                "image_url": {
                    "url": build_media_url(path, "image/png", "图片"),
                },
            }
            if image_role:
                image_item["role"] = image_role
            content.append(image_item)
    if video_path:
        content.append(
            {
                "role": "reference_video",
                "type": "video_url",
                "video_url": {
                    "url": build_media_url(video_path, "video/mp4", "视频", allow_local_file=False),
                },
            }
        )
    return content


def download_video(video_url, output_dir, task_id):
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    parsed = urlsplit(video_url)
    filename = Path(parsed.path).name or f"{task_id}.mp4"
    if not filename.lower().endswith(".mp4"):
        filename = f"{task_id}.mp4"
    save_path = output_dir_path / filename
    response = requests.get(video_url, stream=True, timeout=120)
    response.raise_for_status()
    with save_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return save_path


def submit_task(base_url, headers, model, prompt, image_path, video_path, duration_seconds):
    submit_start_time = time.time()
    try:
        content = build_content(prompt, image_path, video_path)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"构建输入失败: {exc}",
            "prompt": prompt,
            "image_path": image_path,
            "video_path": video_path,
            "submit_start_time": submit_start_time,
            "submit_end_time": time.time(),
        }
    payload = {"model": model, "content": content}
    if duration_seconds is not None:
        payload["duration"] = duration_seconds
    create_response, create_path, create_tried = post_with_fallback(base_url, headers, payload)
    if create_response is None:
        return {
            "ok": False,
            "error": "创建任务接口全部失败",
            "tried": create_tried,
            "prompt": prompt,
            "image_path": image_path,
            "video_path": video_path,
            "submit_start_time": submit_start_time,
            "submit_end_time": time.time(),
        }
    if create_response.status_code >= 400:
        return {
            "ok": False,
            "error": f"创建任务失败 status={create_response.status_code}",
            "response_text": create_response.text[:1200],
            "prompt": prompt,
            "image_path": image_path,
            "video_path": video_path,
            "submit_start_time": submit_start_time,
            "submit_end_time": time.time(),
        }
    try:
        create_data = create_response.json()
    except Exception:
        return {
            "ok": False,
            "error": "创建任务返回非 JSON",
            "prompt": prompt,
            "image_path": image_path,
            "video_path": video_path,
            "submit_start_time": submit_start_time,
            "submit_end_time": time.time(),
        }
    task_id = extract_task_id(create_data)
    if not task_id:
        return {
            "ok": False,
            "error": "未能从响应中解析 task_id",
            "response": create_data,
            "prompt": prompt,
            "image_path": image_path,
            "video_path": video_path,
            "submit_start_time": submit_start_time,
            "submit_end_time": time.time(),
        }
    print(
        f"submit_ok prompt={prompt} image_path={image_path} video_path={video_path} task_id={task_id} path={create_path}"
    )
    return {
        "ok": True,
        "task_id": task_id,
        "prompt": prompt,
        "image_path": image_path,
        "video_path": video_path,
        "duration_seconds": duration_seconds,
        "create_data": create_data,
        "submit_start_time": submit_start_time,
        "submit_end_time": time.time(),
    }


def main():
    script_start_time = time.time()
    args = parse_args()
    api_key = getattr(config, "api_key", "").strip()
    base_url = getattr(config, "base_url", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    model = getattr(config, "model", "doubao-seedance-2-0-fast")
    if args.count < 1:
        print("--count 必须 >= 1")
        sys.exit(1)
    input_prompts = args.prompt or ["一只橘猫在窗边晒太阳，镜头缓慢推进，真实电影光影"]
    input_images = args.image_path or []
    input_videos = args.video_path or []
    if len(input_prompts) == 1 and args.count > 1:
        prompts = [input_prompts[0] for _ in range(args.count)]
    elif len(input_prompts) > 1 and args.count > 1:
        prompts = []
        for prompt in input_prompts:
            prompts.extend([prompt for _ in range(args.count)])
    else:
        prompts = input_prompts
    if not input_images:
        images = [None for _ in range(len(prompts))]
    elif len(prompts) == 1 and len(input_images) > 1:
        images = [input_images]
    elif len(input_images) == 1:
        images = [input_images[0] for _ in range(len(prompts))]
    elif len(input_images) == len(input_prompts) and args.count > 1:
        images = []
        for image_path in input_images:
            images.extend([image_path for _ in range(args.count)])
    elif len(input_images) == len(prompts):
        images = input_images
    else:
        print("图片数量与 prompt 数量不匹配，请传 1 张图片或与 prompt 数量一致的图片数量")
        sys.exit(1)
    if not input_videos:
        videos = [None for _ in range(len(prompts))]
    elif len(input_videos) == 1:
        videos = [input_videos[0] for _ in range(len(prompts))]
    elif len(input_videos) == len(input_prompts) and args.count > 1:
        videos = []
        for video_path in input_videos:
            videos.extend([video_path for _ in range(args.count)])
    elif len(input_videos) == len(prompts):
        videos = input_videos
    else:
        print("视频数量与 prompt 数量不匹配，请传 1 条视频或与 prompt 数量一致的视频数量")
        sys.exit(1)
    if not api_key:
        print("config.py 中未找到 api_key")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"parallel_submit_count={len(prompts)}")
    submissions = []
    submit_workers = min(max(1, args.max_task_workers), len(prompts))
    with ThreadPoolExecutor(max_workers=submit_workers) as executor:
        futures = [
            executor.submit(
                submit_task, base_url, headers, model, prompts[i], images[i], videos[i], args.duration_seconds
            )
            for i in range(len(prompts))
        ]
        for future in as_completed(futures):
            submissions.append(future.result())

    failed_submissions = [s for s in submissions if not s["ok"]]
    if failed_submissions:
        print(json.dumps({"error": "部分任务提交失败", "failed_submissions": failed_submissions}, ensure_ascii=False, indent=2))
        sys.exit(1)

    task_items = []
    for item in submissions:
        task_items.append(
            {
                "task_id": item["task_id"],
                "prompt": item["prompt"],
                "image_path": item["image_path"],
                "video_path": item["video_path"],
                "duration_seconds": item["duration_seconds"],
                "status": "submitted",
                "last_data": item["create_data"],
                "submit_start_time": item["submit_start_time"],
                "submit_end_time": item["submit_end_time"],
            }
        )

    timeout_seconds = args.timeout_seconds
    end_time = time.time() + timeout_seconds
    running_statuses = {"submitted", "queued", "running", "processing", "pending"}
    terminal_statuses = {"succeeded", "success", "completed", "failed", "cancelled", "canceled", "expired"}

    while time.time() < end_time:
        unfinished = [item for item in task_items if item["status"] in running_statuses]
        if not unfinished:
            break
        time.sleep(args.poll_interval_seconds)
        poll_workers = min(max(1, args.max_task_workers), len(unfinished))
        with ThreadPoolExecutor(max_workers=poll_workers) as executor:
            future_map = {
                executor.submit(get_with_fallback, base_url, item["task_id"], headers): item for item in unfinished
            }
            for future in as_completed(future_map):
                item = future_map[future]
                get_response, get_path, get_tried = future.result()
                if get_response is None:
                    item["status"] = "failed"
                    item["error"] = {"message": "查询任务接口全部失败", "tried": get_tried}
                    continue
                if get_response.status_code >= 400:
                    item["status"] = "failed"
                    item["error"] = {"message": f"查询任务失败 status={get_response.status_code}", "text": get_response.text[:1200]}
                    continue
                try:
                    item["last_data"] = get_response.json()
                except Exception:
                    item["status"] = "failed"
                    item["error"] = {"message": "查询任务返回非 JSON"}
                    continue
                status = extract_status(item["last_data"])
                item["status"] = status
                item["status_update_time"] = time.time()
                print(f"poll task_id={item['task_id']} status={status} path={get_path}")
                if status not in terminal_statuses and status not in running_statuses:
                    item["status"] = "running"

    for item in task_items:
        if item["status"] in running_statuses:
            item["status"] = "timeout"

    success_items = [item for item in task_items if item["status"] in {"succeeded", "success", "completed"}]
    failed_items = [item for item in task_items if item["status"] not in {"succeeded", "success", "completed"}]
    for item in task_items:
        if "status_update_time" not in item:
            item["status_update_time"] = time.time()
        item["task_elapsed_seconds"] = round(item["status_update_time"] - item["submit_start_time"], 3)

    script_end_time = time.time()
    avg_elapsed_seconds = 0.0
    if task_items:
        avg_elapsed_seconds = round(sum(i["task_elapsed_seconds"] for i in task_items) / len(task_items), 3)
    result_data = {
        "model": model,
        "summary": {
            "task_count": len(task_items),
            "success_count": len(success_items),
            "failed_count": len(failed_items),
            "total_elapsed_seconds": round(script_end_time - script_start_time, 3),
            "average_task_elapsed_seconds": avg_elapsed_seconds,
        },
        "tasks": task_items,
    }
    result_path = Path(args.result_json)
    result_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result_saved={result_path.resolve()}")
    print(f"success_count={len(success_items)} failed_count={len(failed_items)}")
    print(f"average_task_elapsed_seconds={avg_elapsed_seconds}")

    if failed_items:
        print(json.dumps({"error": "部分任务未成功完成", "failed_items": failed_items}, ensure_ascii=False, indent=2))
        sys.exit(1)

    download_failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_download_workers)) as executor:
        future_map = {}
        for item in success_items:
            video_url = extract_video_url(item["last_data"])
            if not video_url:
                download_failures.append({"task_id": item["task_id"], "error": "任务成功但未返回 video_url"})
                continue
            item["video_url"] = video_url
            future = executor.submit(download_video, video_url, args.output_dir, item["task_id"])
            future_map[future] = item
        for future in as_completed(future_map):
            item = future_map[future]
            try:
                local_video_path = future.result()
                item["video_saved"] = str(local_video_path.resolve())
                print(f"video_saved task_id={item['task_id']} path={item['video_saved']}")
            except Exception as exc:
                download_failures.append({"task_id": item["task_id"], "error": str(exc)})

    if download_failures:
        print(json.dumps({"error": "部分视频下载失败", "download_failures": download_failures}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
