"""Handle report attachment failures and preserve report submission."""

from __future__ import annotations


def _xiaotu_save_uploaded_images_and_ocr_safe(
    files,
    report_token,
    root_base_dir,
    *,
    _xiaotu_image_debug,
    _xiaotu_save_uploaded_images_and_ocr,
):
    try:
        return _xiaotu_save_uploaded_images_and_ocr(files, report_token=report_token, root_base_dir=root_base_dir)
    except Exception as exc:
        return [], "", _xiaotu_image_debug("upload_image_failed", exc, 0)


def _xiaotu_save_inline_html_images_and_ocr_safe(
    html_text,
    report_token,
    root_base_dir,
    *,
    _xiaotu_compact_report_body_for_storage,
    _xiaotu_image_debug,
    _xiaotu_save_inline_html_images_and_ocr,
):
    try:
        return _xiaotu_save_inline_html_images_and_ocr(html_text, report_token=report_token, root_base_dir=root_base_dir)
    except Exception as exc:
        return _xiaotu_compact_report_body_for_storage(html_text), [], "", _xiaotu_image_debug("inline_image_failed", exc, 0)


def _xiaotu_save_remote_html_images_and_ocr_safe(
    html_text,
    report_token,
    agent,
    root_base_dir,
    *,
    _xiaotu_compact_report_body_for_storage,
    _xiaotu_image_debug,
    _xiaotu_save_remote_html_images_and_ocr,
):
    try:
        return _xiaotu_save_remote_html_images_and_ocr(html_text, report_token=report_token, agent=agent, root_base_dir=root_base_dir)
    except Exception as exc:
        return _xiaotu_compact_report_body_for_storage(html_text), [], "", _xiaotu_image_debug("remote_image_failed", exc, 0)


def _xiaotu_save_doc_images_and_ocr_safe(
    agent,
    doc_token,
    doc_url,
    specific_tokens,
    *,
    _xiaotu_image_debug,
    _xiaotu_save_doc_images_and_ocr,
):
    try:
        return _xiaotu_save_doc_images_and_ocr(agent, doc_token, doc_url=doc_url, specific_tokens=specific_tokens)
    except Exception as exc:
        return [], "", _xiaotu_image_debug("doc_image_failed", exc, 0)


def _feishu_upload_image_by_path_safe(
    image_path,
    *,
    _feishu_upload_image_by_path,
):
    try:
        return _feishu_upload_image_by_path(image_path)
    except Exception:
        return ""
