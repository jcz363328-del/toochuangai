"""Image galleries, before-after comparisons and the outpainting preview."""

from __future__ import annotations


def render_outpaint_extension_preview_card(
    uploaded_file,
    top_px,
    bottom_px,
    left_px,
    right_px,
    component_key,
    max_preview_edge,
    drag_state_keys,
    *,
    Image,
    ImageDraw,
    ImageOps,
    OUTPAINT_DRAG_QUERY_KEY,
    OUTPAINT_DRAG_STEP_PX,
    components,
    get_outpaint_extension_limits,
    get_uploaded_file_bytes,
    image_bytes_to_data_url,
    io,
    json,
    st,
) -> None:
    try:
        image_bytes = get_uploaded_file_bytes(uploaded_file)
        with Image.open(io.BytesIO(image_bytes)) as image:
            source = ImageOps.exif_transpose(image).convert("RGBA")
            source_w, source_h = source.size
    except Exception:
        st.caption("扩图预览暂时无法显示，可继续调整参数后处理。")
        return

    limits = get_outpaint_extension_limits(uploaded_file)
    top_px = max(0, min(limits["top"], int(top_px)))
    bottom_px = max(0, min(limits["bottom"], int(bottom_px)))
    left_px = max(0, min(limits["left"], int(left_px)))
    right_px = max(0, min(limits["right"], int(right_px)))
    max_preview_edge = max(260, int(max_preview_edge))
    is_draggable = bool(drag_state_keys)
    top_band = float(limits["top"] if is_draggable else top_px)
    bottom_band = float(limits["bottom"] if is_draggable else bottom_px)
    left_band = float(limits["left"] if is_draggable else left_px)
    right_band = float(limits["right"] if is_draggable else right_px)
    canvas_w = max(source_w + left_band + right_band, 1)
    canvas_h = max(source_h + top_band + bottom_band, 1)
    scale = min(max_preview_edge / canvas_w, max_preview_edge / canvas_h)
    display_w = max(1, int(round(canvas_w * scale)))
    display_h = max(1, int(round(canvas_h * scale)))
    source_x = round(left_band * scale, 2)
    source_y = round(top_band * scale, 2)
    display_source_w = max(1, int(round(source_w * scale)))
    display_source_h = max(1, int(round(source_h * scale)))
    has_extension = (top_px + bottom_px + left_px + right_px) > 0
    current_left = int(round((left_band - left_px) * scale)) if is_draggable else 1
    current_top = int(round((top_band - top_px) * scale)) if is_draggable else 1
    current_right = int(round((left_band + source_w + right_px) * scale)) if is_draggable else max(display_w - 2, 1)
    current_bottom = int(round((top_band + source_h + bottom_px) * scale)) if is_draggable else max(display_h - 2, 1)

    preview_canvas = Image.new("RGBA", (display_w, display_h), (0, 0, 0, 0))
    resized_source = source.resize((display_source_w, display_source_h), Image.Resampling.LANCZOS)
    preview_canvas.alpha_composite(resized_source, (int(round(source_x)), int(round(source_y))))
    draw = ImageDraw.Draw(preview_canvas)

    def draw_dashed_rectangle(box: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = box
        dash = 10
        gap = 7
        width = 2
        for x in range(left, right, dash + gap):
            draw.line((x, top, min(x + dash, right), top), fill=color, width=width)
            draw.line((x, bottom, min(x + dash, right), bottom), fill=color, width=width)
        for y in range(top, bottom, dash + gap):
            draw.line((left, y, left, min(y + dash, bottom)), fill=color, width=width)
            draw.line((right, y, right, min(y + dash, bottom)), fill=color, width=width)

    if has_extension and not is_draggable:
        draw_dashed_rectangle((1, 1, max(display_w - 2, 1), max(display_h - 2, 1)), (139, 117, 255, 245))
    if not is_draggable:
        source_left = int(round(source_x)) + 1
        source_top = int(round(source_y)) + 1
        draw_dashed_rectangle(
            (
                source_left,
                source_top,
                max(source_left + display_source_w - 2, source_left + 1),
                max(source_top + display_source_h - 2, source_top + 1),
            ),
            (255, 255, 255, 235),
        )
    output = io.BytesIO()
    preview_canvas.save(output, format="PNG")
    preview_src = image_bytes_to_data_url(output.getvalue(), "image/png")
    if not is_draggable:
        st.image(output.getvalue(), width=display_w)
        return

    drag_payload = {
        "keys": dict(drag_state_keys or {}),
        "top": top_px,
        "bottom": bottom_px,
        "left": left_px,
        "right": right_px,
        "limits": limits,
        "step": OUTPAINT_DRAG_STEP_PX,
        "source_width": source_w,
        "source_height": source_h,
        "scale": scale,
        "display_width": display_w,
        "display_height": display_h,
        "current_left": current_left,
        "current_top": current_top,
        "current_right": current_right,
        "current_bottom": current_bottom,
        "mode": str(
            st.session_state.get(
                str((drag_state_keys or {}).get("mode") or ""),
                "resize",
            )
            or "resize"
        ),
        "query_key": OUTPAINT_DRAG_QUERY_KEY,
    }
    drag_json = json.dumps(drag_payload, ensure_ascii=False)
    html_content = f"""
    <div id="{component_key}" class="outpaint-drag-root">
      <div class="outpaint-drag-toolbar">
        <button type="button" data-mode="resize">调整扩图范围（改变比例）</button>
        <button type="button" data-mode="position">移动原图位置（不改变比例）</button>
        <span class="outpaint-mode-help"></span>
      </div>
      <div class="outpaint-drag-stage">
        <img class="outpaint-drag-img" src="{preview_src}" alt="扩图范围预览">
        <div class="outpaint-current-box">
          <div class="drag-edge drag-top" data-edge="top"></div>
          <div class="drag-edge drag-bottom" data-edge="bottom"></div>
          <div class="drag-edge drag-left" data-edge="left"></div>
          <div class="drag-edge drag-right" data-edge="right"></div>
          <div class="drag-corner drag-top-left" data-edge="top-left"></div>
          <div class="drag-corner drag-top-right" data-edge="top-right"></div>
          <div class="drag-corner drag-bottom-left" data-edge="bottom-left"></div>
          <div class="drag-corner drag-bottom-right" data-edge="bottom-right"></div>
        </div>
        <div class="outpaint-source-handle" title="按住并拖动原图，调整它在最终画布中的位置"></div>
      </div>
      <div class="outpaint-drag-values">
        <span>上 <b data-value="top"></b></span>
        <span>下 <b data-value="bottom"></b></span>
        <span>左 <b data-value="left"></b></span>
        <span>右 <b data-value="right"></b></span>
      </div>
      <div class="outpaint-target-summary">
        目标画布 <b data-value="target"></b> · 宽高比 <b data-value="ratio"></b> · 原图坐标 <b data-value="position"></b>
      </div>
    </div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        color: rgba(245, 247, 255, 0.92);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      #{component_key} {{
        width: {display_w}px;
        max-width: 100%;
        margin: 0 auto;
      }}
      #{component_key} .outpaint-drag-toolbar {{
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 8px;
      }}
      #{component_key} .outpaint-drag-toolbar button {{
        appearance: none;
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 9px;
        padding: 7px 10px;
        background: rgba(7, 15, 31, 0.68);
        color: rgba(225, 229, 255, 0.82);
        font-size: 12px;
        cursor: pointer;
      }}
      #{component_key} .outpaint-drag-toolbar button.is-active {{
        border-color: rgba(139, 117, 255, 0.95);
        background: rgba(104, 76, 232, 0.30);
        color: #ffffff;
      }}
      #{component_key} .outpaint-mode-help {{
        min-width: 0;
        color: rgba(214, 219, 255, 0.72);
        font-size: 11px;
      }}
      #{component_key} .outpaint-drag-stage {{
        position: relative;
        width: min({display_w}px, 100%);
        aspect-ratio: {display_w} / {display_h};
        height: auto;
        max-width: 100%;
        background: rgba(4, 10, 24, 0.56);
        border-radius: 12px;
        overflow: hidden;
        touch-action: none;
      }}
      #{component_key} .outpaint-drag-img {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        user-select: none;
        -webkit-user-drag: none;
        pointer-events: none;
        transform: translate3d(0, 0, 0);
        transform-origin: 0 0;
      }}
      #{component_key} .outpaint-current-box {{
        position: absolute;
        box-sizing: border-box;
        border: 2px dashed rgba(139, 117, 255, 0.98);
        box-shadow: 0 0 0 1px rgba(139, 117, 255, 0.35), 0 0 18px rgba(139, 117, 255, 0.35);
        overflow: visible;
        z-index: 2;
      }}
      #{component_key} .outpaint-source-handle {{
        position: absolute;
        box-sizing: border-box;
        z-index: 3;
        border: 2px dashed rgba(255, 255, 255, 0.92);
        background: rgba(255, 255, 255, 0.02);
        cursor: grab;
        touch-action: none;
      }}
      #{component_key} .outpaint-source-handle:active {{
        cursor: grabbing;
      }}
      #{component_key}[data-mode="resize"] .outpaint-source-handle {{
        pointer-events: none;
        background: transparent;
      }}
      #{component_key}[data-mode="position"] .drag-edge,
      #{component_key}[data-mode="position"] .drag-corner {{
        pointer-events: none;
        opacity: 0.34;
      }}
      #{component_key} .drag-edge {{
        position: absolute;
        background: rgba(139, 117, 255, 0.18);
      }}
      #{component_key} .drag-corner {{
        position: absolute;
        width: 18px;
        height: 18px;
        border-radius: 999px;
        background: rgba(139, 117, 255, 0.98);
        border: 2px solid rgba(255, 255, 255, 0.95);
        box-shadow: 0 0 16px rgba(139, 117, 255, 0.55);
        z-index: 3;
      }}
      #{component_key} .drag-edge:hover,
      #{component_key} .drag-corner:hover {{
        background: rgba(160, 139, 255, 1);
      }}
      #{component_key} .drag-top, #{component_key} .drag-bottom {{
        left: -8px;
        right: -8px;
        height: 16px;
        cursor: ns-resize;
      }}
      #{component_key} .drag-top {{ top: -9px; }}
      #{component_key} .drag-bottom {{ bottom: -9px; }}
      #{component_key} .drag-left, #{component_key} .drag-right {{
        top: -8px;
        bottom: -8px;
        width: 16px;
        cursor: ew-resize;
      }}
      #{component_key} .drag-left {{ left: -9px; }}
      #{component_key} .drag-right {{ right: -9px; }}
      #{component_key} .drag-top-left {{
        left: -10px;
        top: -10px;
        cursor: nwse-resize;
      }}
      #{component_key} .drag-top-right {{
        right: -10px;
        top: -10px;
        cursor: nesw-resize;
      }}
      #{component_key} .drag-bottom-left {{
        left: -10px;
        bottom: -10px;
        cursor: nesw-resize;
      }}
      #{component_key} .drag-bottom-right {{
        right: -10px;
        bottom: -10px;
        cursor: nwse-resize;
      }}
      #{component_key} .outpaint-drag-values {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 6px;
        margin-top: 8px;
        font-size: 11px;
        color: rgba(214, 219, 255, 0.78);
      }}
      #{component_key} .outpaint-drag-values span {{
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
        padding: 5px 6px;
        background: rgba(7, 15, 31, 0.56);
        text-align: center;
      }}
      #{component_key} .outpaint-drag-values b {{
        color: #ffffff;
      }}
      #{component_key} .outpaint-target-summary {{
        margin-top: 6px;
        color: rgba(214, 219, 255, 0.74);
        font-size: 11px;
        text-align: center;
      }}
      #{component_key} .outpaint-target-summary b {{
        color: #ffffff;
      }}
    </style>
    <script>
      const config_{component_key} = {drag_json};
      const root_{component_key} = document.getElementById("{component_key}");
      const stage_{component_key} = root_{component_key}.querySelector(".outpaint-drag-stage");
      const box_{component_key} = root_{component_key}.querySelector(".outpaint-current-box");
      const previewImage_{component_key} = root_{component_key}.querySelector(".outpaint-drag-img");
      const sourceHandle_{component_key} = root_{component_key}.querySelector(".outpaint-source-handle");
      const modeHelp_{component_key} = root_{component_key}.querySelector(".outpaint-mode-help");
      const modeButtons_{component_key} = Array.from(
        root_{component_key}.querySelectorAll(".outpaint-drag-toolbar [data-mode]")
      );
      const valueNodes_{component_key} = {{
        top: root_{component_key}.querySelector('[data-value="top"]'),
        bottom: root_{component_key}.querySelector('[data-value="bottom"]'),
        left: root_{component_key}.querySelector('[data-value="left"]'),
        right: root_{component_key}.querySelector('[data-value="right"]'),
      }};
      const targetNode_{component_key} = root_{component_key}.querySelector('[data-value="target"]');
      const ratioNode_{component_key} = root_{component_key}.querySelector('[data-value="ratio"]');
      const positionNode_{component_key} = root_{component_key}.querySelector('[data-value="position"]');
      let mode_{component_key} = ["position", "resize"].includes(String(config_{component_key}.mode || ""))
        ? String(config_{component_key}.mode)
        : "resize";
      let values_{component_key} = {{
        top: Number(config_{component_key}.top || 0),
        bottom: Number(config_{component_key}.bottom || 0),
        left: Number(config_{component_key}.left || 0),
        right: Number(config_{component_key}.right || 0),
      }};
      const directionLimit_{component_key} = (direction) => {{
        return Number((config_{component_key}.limits || {{}})[direction] || 0);
      }};
      const roundValue_{component_key} = (value, direction) => {{
        const max = directionLimit_{component_key}(direction);
        const step = Number(config_{component_key}.step || 50);
        const numericValue = Math.max(0, Number(value || 0));
        if (max > 0 && numericValue >= max - step / 2) return max;
        return Math.max(0, Math.min(max, Math.round(numericValue / step) * step));
      }};
      const renderScale_{component_key} = () => {{
        const rect = stage_{component_key}.getBoundingClientRect();
        return {{
          x: Math.max(rect.width, 1) / Math.max(Number(config_{component_key}.display_width || 1), 1),
          y: Math.max(rect.height, 1) / Math.max(Number(config_{component_key}.display_height || 1), 1),
        }};
      }};
      const applyBox_{component_key} = () => {{
        const baseScale = Number(config_{component_key}.scale || 1);
        const stageScale = renderScale_{component_key}();
        const scaleX = baseScale * stageScale.x;
        const scaleY = baseScale * stageScale.y;
        const maxX = directionLimit_{component_key}("left");
        const maxY = directionLimit_{component_key}("top");
        const sourceWidth = Number(config_{component_key}.source_width || 1);
        const sourceHeight = Number(config_{component_key}.source_height || 1);
        const targetWidth = sourceWidth + values_{component_key}.left + values_{component_key}.right;
        const targetHeight = sourceHeight + values_{component_key}.top + values_{component_key}.bottom;
        const stageWidth = Number(config_{component_key}.display_width || 1) * stageScale.x;
        const stageHeight = Number(config_{component_key}.display_height || 1) * stageScale.y;
        let left = (maxX - values_{component_key}.left) * scaleX;
        let top = (maxY - values_{component_key}.top) * scaleY;
        let sourceLeft = maxX * scaleX;
        let sourceTop = maxY * scaleY;
        if (mode_{component_key} === "position") {{
          left = Math.max((stageWidth - targetWidth * scaleX) / 2, 0);
          top = Math.max((stageHeight - targetHeight * scaleY) / 2, 0);
          sourceLeft = left + values_{component_key}.left * scaleX;
          sourceTop = top + values_{component_key}.top * scaleY;
        }}
        const right = left + targetWidth * scaleX;
        const bottom = top + targetHeight * scaleY;
        box_{component_key}.style.left = `${{left}}px`;
        box_{component_key}.style.top = `${{top}}px`;
        box_{component_key}.style.width = `${{Math.max(right - left, 1)}}px`;
        box_{component_key}.style.height = `${{Math.max(bottom - top, 1)}}px`;
        const baseSourceLeft = maxX * scaleX;
        const baseSourceTop = maxY * scaleY;
        previewImage_{component_key}.style.transform = `translate3d(${{sourceLeft - baseSourceLeft}}px, ${{sourceTop - baseSourceTop}}px, 0)`;
        sourceHandle_{component_key}.style.left = `${{sourceLeft}}px`;
        sourceHandle_{component_key}.style.top = `${{sourceTop}}px`;
        sourceHandle_{component_key}.style.width = `${{Math.max(sourceWidth * scaleX, 1)}}px`;
        sourceHandle_{component_key}.style.height = `${{Math.max(sourceHeight * scaleY, 1)}}px`;
        root_{component_key}.dataset.mode = mode_{component_key};
        modeButtons_{component_key}.forEach((button) => {{
          button.classList.toggle("is-active", button.dataset.mode === mode_{component_key});
        }});
        if (modeHelp_{component_key}) {{
          modeHelp_{component_key}.textContent = mode_{component_key} === "position"
            ? "只移动原图位置，目标画布尺寸和比例不变"
            : "拖动紫色边线或四角，实时改变目标尺寸和比例";
        }}
        Object.entries(valueNodes_{component_key}).forEach(([key, node]) => {{
          if (node) node.textContent = `${{values_{component_key}[key]}}px`;
        }});
        if (targetNode_{component_key}) {{
          targetNode_{component_key}.textContent = `${{targetWidth}}×${{targetHeight}}px`;
        }}
        if (ratioNode_{component_key}) {{
          ratioNode_{component_key}.textContent = (targetWidth / Math.max(targetHeight, 1)).toFixed(3);
        }}
        if (positionNode_{component_key}) {{
          positionNode_{component_key}.textContent = `X=${{values_{component_key}.left}}, Y=${{values_{component_key}.top}}`;
        }}
      }};
      const updateFromPointer_{component_key} = (edge, event) => {{
        const rect = stage_{component_key}.getBoundingClientRect();
        const baseScale = Number(config_{component_key}.scale || 1);
        const stageScale = renderScale_{component_key}();
        const scaleX = baseScale * stageScale.x;
        const scaleY = baseScale * stageScale.y;
        const maxX = directionLimit_{component_key}("left");
        const maxY = directionLimit_{component_key}("top");
        const sourceWidth = Number(config_{component_key}.source_width || 1);
        const sourceHeight = Number(config_{component_key}.source_height || 1);
        const x = (event.clientX - rect.left) / scaleX;
        const y = (event.clientY - rect.top) / scaleY;
        if (edge.includes("left")) values_{component_key}.left = roundValue_{component_key}(maxX - x, "left");
        if (edge.includes("top")) values_{component_key}.top = roundValue_{component_key}(maxY - y, "top");
        if (edge.includes("right")) values_{component_key}.right = roundValue_{component_key}(x - maxX - sourceWidth, "right");
        if (edge.includes("bottom")) values_{component_key}.bottom = roundValue_{component_key}(y - maxY - sourceHeight, "bottom");
        applyBox_{component_key}();
      }};
      const commit_{component_key} = () => {{
        try {{
          const parentWindow = window.parent || window;
          const next = new URL(parentWindow.location.href);
          next.searchParams.set(config_{component_key}.query_key, JSON.stringify({{
            keys: config_{component_key}.keys || {{}},
            top: values_{component_key}.top,
            bottom: values_{component_key}.bottom,
            left: values_{component_key}.left,
            right: values_{component_key}.right,
            mode: mode_{component_key},
            limits: config_{component_key}.limits || {{}},
            step: Number(config_{component_key}.step || 1),
          }}));
          parentWindow.location.href = next.toString();
        }} catch (error) {{}}
      }};
      modeButtons_{component_key}.forEach((button) => {{
        button.addEventListener("click", () => {{
          const nextMode = String(button.dataset.mode || "");
          if (!["position", "resize"].includes(nextMode)) return;
          mode_{component_key} = nextMode;
          applyBox_{component_key}();
        }});
      }});
      root_{component_key}.querySelectorAll(".drag-edge, .drag-corner").forEach((handle) => {{
        let dragging = false;
        const edge = handle.dataset.edge;
        handle.addEventListener("pointerdown", (event) => {{
          if (mode_{component_key} !== "resize") return;
          dragging = true;
          handle.setPointerCapture && handle.setPointerCapture(event.pointerId);
          updateFromPointer_{component_key}(edge, event);
          event.preventDefault();
        }});
        handle.addEventListener("pointermove", (event) => {{
          if (!dragging) return;
          updateFromPointer_{component_key}(edge, event);
          event.preventDefault();
        }});
        const stop = () => {{
          if (!dragging) return;
          dragging = false;
          commit_{component_key}();
        }};
        handle.addEventListener("pointerup", stop);
        handle.addEventListener("pointercancel", stop);
        handle.addEventListener("lostpointercapture", stop);
      }});
      let sourceDragging_{component_key} = false;
      let sourceDragStart_{component_key} = null;
      const clampMovedPair_{component_key} = (value, total, primaryDirection, secondaryDirection) => {{
        const primaryLimit = directionLimit_{component_key}(primaryDirection);
        const secondaryLimit = directionLimit_{component_key}(secondaryDirection);
        const minimum = Math.max(0, total - secondaryLimit);
        const maximum = Math.min(primaryLimit, total);
        const step = Math.max(Number(config_{component_key}.step || 1), 1);
        return Math.max(minimum, Math.min(maximum, Math.round(Number(value || 0) / step) * step));
      }};
      sourceHandle_{component_key}.addEventListener("pointerdown", (event) => {{
        if (mode_{component_key} !== "position") return;
        sourceDragging_{component_key} = true;
        sourceDragStart_{component_key} = {{
          clientX: event.clientX,
          clientY: event.clientY,
          top: values_{component_key}.top,
          bottom: values_{component_key}.bottom,
          left: values_{component_key}.left,
          right: values_{component_key}.right,
        }};
        sourceHandle_{component_key}.setPointerCapture &&
          sourceHandle_{component_key}.setPointerCapture(event.pointerId);
        event.preventDefault();
      }});
      sourceHandle_{component_key}.addEventListener("pointermove", (event) => {{
        if (!sourceDragging_{component_key} || !sourceDragStart_{component_key}) return;
        const baseScale = Number(config_{component_key}.scale || 1);
        const stageScale = renderScale_{component_key}();
        const scaleX = Math.max(baseScale * stageScale.x, 0.0001);
        const scaleY = Math.max(baseScale * stageScale.y, 0.0001);
        const horizontalTotal = sourceDragStart_{component_key}.left + sourceDragStart_{component_key}.right;
        const verticalTotal = sourceDragStart_{component_key}.top + sourceDragStart_{component_key}.bottom;
        const nextLeft = clampMovedPair_{component_key}(
          sourceDragStart_{component_key}.left + (event.clientX - sourceDragStart_{component_key}.clientX) / scaleX,
          horizontalTotal,
          "left",
          "right",
        );
        const nextTop = clampMovedPair_{component_key}(
          sourceDragStart_{component_key}.top + (event.clientY - sourceDragStart_{component_key}.clientY) / scaleY,
          verticalTotal,
          "top",
          "bottom",
        );
        values_{component_key}.left = nextLeft;
        values_{component_key}.right = horizontalTotal - nextLeft;
        values_{component_key}.top = nextTop;
        values_{component_key}.bottom = verticalTotal - nextTop;
        applyBox_{component_key}();
        event.preventDefault();
      }});
      const stopSourceDrag_{component_key} = () => {{
        if (!sourceDragging_{component_key}) return;
        sourceDragging_{component_key} = false;
        sourceDragStart_{component_key} = null;
        commit_{component_key}();
      }};
      sourceHandle_{component_key}.addEventListener("pointerup", stopSourceDrag_{component_key});
      sourceHandle_{component_key}.addEventListener("pointercancel", stopSourceDrag_{component_key});
      sourceHandle_{component_key}.addEventListener("lostpointercapture", stopSourceDrag_{component_key});
      window.addEventListener("resize", applyBox_{component_key});
      applyBox_{component_key}();
    </script>
    """
    components.html(html_content, height=max(display_h + 140, 400), scrolling=False)


def render_zoomable_image_gallery(
    images,
    columns,
    thumb_height,
    component_key,
    fit_mode,
    max_width_percent,
    context_delete_token,
    compress_preview,
    include_full_src,
    full_images,
    download_names,
    direct_src,
    embed_full_src,
    allow_native_image_download,
    native_fullscreen_context_menu,
    *,
    Any,
    HISTORY_STATIC_ROUTE_PREFIX,
    JIMENG_UPLOAD_ROUTE_PREFIX,
    UPLOAD_DELETE_QUERY_KEY,
    build_gallery_item,
    get_history_public_base_url,
    get_image_extension_from_mime,
    get_jimeng_public_upload_base_url,
    json,
    os,
    st,
    urllib,
) -> None:
    items: list[dict[str, Any]] = []
    normalized_full_images = list(full_images or [])
    normalized_download_names = list(download_names or [])
    for index, image_source in enumerate(images):
        item = build_gallery_item(
            image_source,
            compress_preview=compress_preview,
            include_full_src=include_full_src,
            full_image_source=(
                normalized_full_images[index]
                if index < len(normalized_full_images)
                else ""
            ),
            direct_src=direct_src,
            embed_full_src=embed_full_src,
        )
        if item:
            if index < len(normalized_download_names):
                download_name = str(normalized_download_names[index] or "").strip()
                if download_name:
                    item["download_name"] = download_name
            if not item.get("download_name") and str(item.get("full_src") or "").startswith("data:"):
                original_mime = str(item["full_src"]).split(";", 1)[0].removeprefix("data:")
                extension = get_image_extension_from_mime(original_mime)
                item["download_name"] = f"{component_key}_{index + 1}{extension}"
            items.append(item)
    if not items:
        return
    gap = 12
    thumb_style = f"height: {thumb_height}px;" if thumb_height else "height: auto;"
    payload = json.dumps(items, ensure_ascii=False)
    managed_image_hosts = json.dumps(sorted({
        urllib.parse.urlsplit(base).hostname for base in
        (get_history_public_base_url(), get_jimeng_public_upload_base_url())
        if urllib.parse.urlsplit(base).hostname
    }))
    delete_token = json.dumps(str(context_delete_token or ""))
    allow_native_download = json.dumps(bool(allow_native_image_download))
    native_fullscreen_menu = json.dumps(bool(native_fullscreen_context_menu))
    html_content = f"""
    <div id="{component_key}" class="zoom-gallery-root" style="max-width: {max_width_percent}%; margin: 0 auto;">
      <div class="zoom-gallery-grid" style="grid-template-columns: repeat({columns}, minmax(0, 1fr)); gap: {gap}px;">
      </div>
    </div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
      }}
      .zoom-gallery-grid {{
        display: grid;
      }}
      .zoom-thumb-wrap {{
        position: relative;
        width: 100%;
      }}
      .zoom-thumb {{
        width: 100%;
        {thumb_style}
        object-fit: {fit_mode};
        display: block;
        cursor: zoom-in;
        background: transparent;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.10);
        box-sizing: border-box;
      }}
      .zoom-thumb-delete {{
        appearance: none;
        position: absolute;
        top: 6px;
        right: 6px;
        z-index: 3;
        width: 24px;
        height: 24px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.92);
        background: rgba(255, 77, 90, 0.96);
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 15px;
        font-weight: 800;
        line-height: 1;
        cursor: pointer;
        user-select: none;
        backdrop-filter: blur(3px);
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.34);
        opacity: 1;
      }}
      .zoom-thumb-delete:hover {{
        background: rgba(255, 36, 74, 1);
        border-color: rgba(255, 255, 255, 1);
        color: #ffffff;
      }}
    </style>
    <script>
      const images_{component_key} = {payload};
      const grid_{component_key} = document.querySelector("#{component_key} .zoom-gallery-grid");
      const hostWindow_{component_key} = (() => {{
        try {{
          return window.parent;
        }} catch (e) {{
          return window;
        }}
      }})();
      const hostDoc_{component_key} = (() => {{
        try {{
          return window.parent.document;
        }} catch (e) {{
          return document;
        }}
      }})();

      function normalizeViewerSrc_{component_key}(src) {{
        const raw = String(src || "").trim();
        if (!raw || raw.startsWith("data:")) {{
          return raw;
        }}
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const isStaticImageRoute =
            (parsed.hostname === hostWindow_{component_key}.location.hostname || {managed_image_hosts}.includes(parsed.hostname)) &&
            (parsed.pathname.startsWith("{HISTORY_STATIC_ROUTE_PREFIX}/") ||
            parsed.pathname.startsWith("{JIMENG_UPLOAD_ROUTE_PREFIX}/"));
          if (!isStaticImageRoute) {{
            return parsed.toString();
          }}
          if ({json.dumps(os.getenv("TC_SINGLE_PORT") == "1")}) {{
            return new URL(parsed.pathname + parsed.search + parsed.hash,
              hostWindow_{component_key}.location.origin).toString();
          }}
          const currentProtocol = hostWindow_{component_key}.location.protocol || parsed.protocol;
          const currentHostname = hostWindow_{component_key}.location.hostname || parsed.hostname;
          const currentPort = parsed.port ? ":" + parsed.port : "";
          return `${{currentProtocol}}//${{currentHostname}}${{currentPort}}${{parsed.pathname}}${{parsed.search}}${{parsed.hash}}`;
        }} catch (e) {{
          return raw;
        }}
      }}

      function deriveEagleFileName_{component_key}(src, index) {{
        const fallbackName = "{component_key}_" + String(index + 1) + ".png";
        const configuredName = String(
          (images_{component_key}[index] && images_{component_key}[index].download_name) || ""
        ).trim();
        if (configuredName) return configuredName;
        const raw = String(src || "").trim();
        if (!raw) return fallbackName;
        if (raw.startsWith("data:")) return fallbackName;
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const baseName = decodeURIComponent((parsed.pathname || "").split("/").pop() || "").trim();
          return baseName || fallbackName;
        }} catch (e) {{
          return fallbackName;
        }}
      }}

      async function downloadOriginal_{component_key}(src, name, saveAs = false) {{
        const originalSrc = normalizeViewerSrc_{component_key}(src);
        const originalName = name || "original.png";
        const clickDownload = (href) => {{
          const link = hostDoc_{component_key}.createElement("a");
          link.href = href;
          link.download = originalName;
          const viewer = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
          const dialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
          const linkHost = viewer && viewer.classList.contains("active") ? viewer : (dialog || hostDoc_{component_key}.body);
          linkHost.appendChild(link);
          link.click();
          link.remove();
        }};
        try {{
          if (!originalSrc) throw new Error("missing original");
          const parsed = new URL(originalSrc, hostWindow_{component_key}.location.href);
          const isStaticImageRoute =
            (parsed.hostname === hostWindow_{component_key}.location.hostname || {managed_image_hosts}.includes(parsed.hostname)) &&
            (parsed.pathname.startsWith("{HISTORY_STATIC_ROUTE_PREFIX}/") ||
            parsed.pathname.startsWith("{JIMENG_UPLOAD_ROUTE_PREFIX}/"));
          const canSaveAs = saveAs && typeof hostWindow_{component_key}.showSaveFilePicker === "function";
          if (isStaticImageRoute && !canSaveAs) {{
            // Let the server stream the original as an attachment. This stays
            // within the user's click and avoids CORS/blob and memory limits.
            parsed.searchParams.set("download", "1");
            parsed.searchParams.set("filename", originalName);
            clickDownload(parsed.toString());
            return;
          }}
          // Open the picker before awaiting a network request: browsers require
          // the original user gesture, which a slow fetch would otherwise lose.
          const handle = canSaveAs
            ? await hostWindow_{component_key}.showSaveFilePicker({{suggestedName: originalName}})
            : null;
          const response = await hostWindow_{component_key}.fetch(originalSrc);
          if (!response.ok) throw new Error("original HTTP " + response.status);
          const blob = await response.blob();
          if (!blob.size || !blob.type.toLowerCase().startsWith("image/")) {{
            throw new Error("invalid original image response");
          }}
          if (handle) {{
            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
            return;
          }}
          const blobUrl = hostWindow_{component_key}.URL.createObjectURL(blob);
          clickDownload(blobUrl);
          hostWindow_{component_key}.setTimeout(() => hostWindow_{component_key}.URL.revokeObjectURL(blobUrl), 60000);
        }} catch (error) {{
          if (error && error.name === "AbortError") return;
          showEagleToast_{component_key}("原图下载失败，请刷新后重试；原文件可能已被移除。");
        }}
      }}

      async function eagleFetch_{component_key}(url, options) {{
        const controller = new hostWindow_{component_key}.AbortController();
        const timeout = hostWindow_{component_key}.setTimeout(() => controller.abort(), 60000);
        try {{
          return await hostWindow_{component_key}.fetch(url, {{...options, signal: controller.signal}});
        }} finally {{
          hostWindow_{component_key}.clearTimeout(timeout);
        }}
      }}

      function ensureEagleUi_{component_key}() {{
        const activeViewer = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const activeDialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
        const uiHost = activeViewer && activeViewer.classList.contains("active")
          ? activeViewer : (activeDialog || hostDoc_{component_key}.body);
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-style")) {{
          const style = hostDoc_{component_key}.createElement("style");
          style.id = "lashforge-eagle-style";
          style.textContent = `
            #lashforge-eagle-menu {{
              position: fixed;
              min-width: 168px;
              padding: 6px;
              border-radius: 12px;
              background: rgba(9, 17, 35, 0.96);
              border: 1px solid rgba(126, 166, 255, 0.22);
              box-shadow: 0 18px 40px rgba(0, 0, 0, 0.34);
              z-index: 1000001;
              display: none;
            }}
            #lashforge-eagle-menu button {{
              width: 100%;
              border: 0;
              border-radius: 9px;
              background: transparent;
              color: #eef4ff;
              padding: 9px 10px;
              text-align: left;
              font-size: 13px;
              cursor: pointer;
            }}
            #lashforge-eagle-menu button:hover {{
              background: rgba(126, 166, 255, 0.16);
            }}
            #lashforge-eagle-toast {{
              position: fixed;
              right: 18px;
              bottom: 18px;
              z-index: 1000002;
              padding: 10px 14px;
              border-radius: 12px;
              background: rgba(9, 17, 35, 0.94);
              border: 1px solid rgba(126, 166, 255, 0.22);
              color: #eef4ff;
              font-size: 12px;
              box-shadow: 0 14px 34px rgba(0, 0, 0, 0.28);
              opacity: 0;
              pointer-events: none;
              transition: opacity .16s ease;
            }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        const existingMenu = hostDoc_{component_key}.getElementById("lashforge-eagle-menu");
        if (existingMenu && existingMenu.dataset.version !== "20261124-2") existingMenu.remove();
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-menu")) {{
          const menu = hostDoc_{component_key}.createElement("div");
          menu.id = "lashforge-eagle-menu";
          menu.dataset.version = "20261124-2";
          menu.innerHTML = ''
            + '<button type="button" id="lashforge-download-image">下载原图</button>'
            + '<button type="button" id="lashforge-save-as-image">原图另存为...</button>'
            + '<button type="button" id="lashforge-save-to-eagle">保存到 Eagle</button>';
          uiHost.appendChild(menu);
          hostWindow_{component_key}.__lashforgeEagleMenuState = {{}};
          const hideMenu = () => {{
            menu.style.display = "none";
          }};
          hostDoc_{component_key}.addEventListener("click", hideMenu, true);
          hostDoc_{component_key}.addEventListener("scroll", hideMenu, true);
          hostWindow_{component_key}.addEventListener("blur", hideMenu);
          hostDoc_{component_key}.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") hideMenu();
          }}, true);
          menu.querySelector("#lashforge-download-image").addEventListener("click", async () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            await downloadOriginal_{component_key}(state.src, state.name);
          }});
          menu.querySelector("#lashforge-save-as-image").addEventListener("click", async () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            await downloadOriginal_{component_key}(state.src, state.name, true);
          }});
          menu.querySelector("#lashforge-save-to-eagle").addEventListener("click", async () => {{
            const state = hostWindow_{component_key}.__lashforgeEagleMenuState || {{}};
            hideMenu();
            if (!state.src) {{
              return;
            }}
            const saveButton = menu.querySelector("#lashforge-save-to-eagle");
            if (saveButton.disabled) return;
            saveButton.disabled = true;
            let stage = "connect";
            try {{
              if (!hostWindow_{component_key}.isSecureContext) {{
                showEagleToast_{component_key}("当前 HTTP 页面无法直连 Eagle。请放大原图后按 Alt + 右键，用 Eagle 浏览器扩展保存；也可下载原图后导入。", 12000);
                return;
              }}
              showEagleToast_{component_key}("正在保存到 Eagle…");
              // Request local access while the click is still fresh, before
              // spending time loading a large original image.
              const info = await eagleFetch_{component_key}("http://localhost:41595/api/application/info", {{
                targetAddressSpace: "loopback"
              }});
              if (!info.ok) throw new Error("Eagle 连接失败（" + info.status + "）");
              stage = "image";
              // Read with the browser session: Eagle cannot resolve blob URLs or
              // access images protected by this site's login cookies.
              const imageResponse = await eagleFetch_{component_key}(state.src, {{
                credentials: "same-origin"
              }});
              if (!imageResponse.ok) throw new Error("原图读取失败（" + imageResponse.status + "）");
              const blob = await imageResponse.blob();
              if (!blob.size || !blob.type.startsWith("image/")) {{
                throw new Error("原图不可用或登录已过期，请刷新页面后重试");
              }}
              const imageData = await new Promise((resolve, reject) => {{
                const reader = new hostWindow_{component_key}.FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () => reject(new Error("原图读取失败"));
                reader.readAsDataURL(blob);
              }});
              stage = "eagle";
              // A plain-text JSON body matches Eagle's API example and avoids
              // the extra application/json CORS preflight on the local service.
              const response = await eagleFetch_{component_key}("http://localhost:41595/api/item/addFromURL", {{
                method: "POST",
                targetAddressSpace: "loopback",
                body: JSON.stringify({{
                  url: imageData,
                  name: state.name || "{component_key}.png",
                  website: hostWindow_{component_key}.location.href,
                  modificationTime: Date.now()
                }})
              }});
              stage = "response";
              const result = await response.json();
              if (!response.ok || !result || result.status !== "success") {{
                throw new Error((result && (result.message || result.status)) || "Eagle 返回异常（" + response.status + "）");
              }}
              showEagleToast_{component_key}("已保存到 Eagle");
            }} catch (error) {{
              let message = error && error.message ? error.message : "未知错误";
              if (stage === "eagle" || stage === "connect") {{
                message = error && error.name === "AbortError"
                  ? "Eagle 响应超时，请先检查素材库是否已保存"
                  : "无法连接本机 Eagle，请确认已启动，并允许浏览器访问本地网络";
              }} else if (stage === "image" && error && error.name === "TypeError") {{
                message = "无法读取原图，请刷新页面后重试";
              }}
              showEagleToast_{component_key}("保存到 Eagle 失败：" + message, 8000);
            }} finally {{
              saveButton.disabled = false;
            }}
          }});
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-eagle-toast")) {{
          const toast = hostDoc_{component_key}.createElement("div");
          toast.id = "lashforge-eagle-toast";
          uiHost.appendChild(toast);
        }}
      }}

      function showEagleToast_{component_key}(message, duration = 1800) {{
        ensureEagleUi_{component_key}();
        const toast = hostDoc_{component_key}.getElementById("lashforge-eagle-toast");
        if (!toast) return;
        const viewer = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const dialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
        const toastHost = viewer && viewer.classList.contains("active") ? viewer : (dialog || hostDoc_{component_key}.body);
        if (toast.parentElement !== toastHost) toastHost.appendChild(toast);
        toast.inert = false;
        toast.removeAttribute("inert");
        toast.textContent = String(message || "");
        toast.style.opacity = "1";
        hostWindow_{component_key}.clearTimeout(hostWindow_{component_key}.__lashforgeEagleToastTimer);
        hostWindow_{component_key}.__lashforgeEagleToastTimer = hostWindow_{component_key}.setTimeout(() => {{
          toast.style.opacity = "0";
        }}, duration);
      }}

      function openEagleMenu_{component_key}(event, src, index) {{
        ensureEagleUi_{component_key}();
        const menu = hostDoc_{component_key}.getElementById("lashforge-eagle-menu");
        if (!menu) return;
        // A modal dialog is in the browser's top layer. A menu on body is
        // inert behind it, regardless of z-index. Keep it with its target.
        const viewer = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const frame = window.frameElement;
        const dialog = frame && frame.closest('dialog, [role="dialog"]');
        const menuHost = viewer && viewer.classList.contains("active")
          ? viewer : (dialog || hostDoc_{component_key}.body);
        if (menu.parentElement !== menuHost) menuHost.appendChild(menu);
        menu.inert = false;
        menu.removeAttribute("inert");
        const normalizedSrc = normalizeViewerSrc_{component_key}(src);
        hostWindow_{component_key}.__lashforgeEagleMenuState = {{
          src: normalizedSrc,
          name: deriveEagleFileName_{component_key}(normalizedSrc, index)
        }};
        const menuWidth = 168;
        const menuHeight = 126;
        const maxLeft = Math.max((hostWindow_{component_key}.innerWidth || 0) - menuWidth - 12, 12);
        const maxTop = Math.max((hostWindow_{component_key}.innerHeight || 0) - menuHeight - 12, 12);
        menu.style.left = Math.min(Math.max(event.clientX, 12), maxLeft) + "px";
        menu.style.top = Math.min(Math.max(event.clientY, 12), maxTop) + "px";
        menu.style.display = "block";
      }}

      function ensureOverlay_{component_key}() {{
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-style")) {{
          const style = hostDoc_{component_key}.createElement("style");
          style.id = "lashforge-fullscreen-style";
          style.textContent = `
            #lashforge-fullscreen-viewer {{
              position: fixed;
              inset: 0;
              z-index: 999999;
              background: rgba(3, 8, 22, 0.96);
              display: none;
              align-items: center;
              justify-content: center;
              overflow: hidden;
            }}
            #lashforge-fullscreen-viewer.active {{
              display: flex;
            }}
            #lashforge-fullscreen-viewer img {{
              max-width: 96vw;
              max-height: 96vh;
              object-fit: contain;
              transform-origin: center center;
              transition: transform 0.08s linear;
              user-select: none;
              -webkit-user-drag: none;
              cursor: grab;
            }}
            #lashforge-fullscreen-viewer img.dragging {{
              cursor: grabbing;
            }}
            #lashforge-fullscreen-close {{
              position: fixed;
              top: 18px;
              right: 18px;
              z-index: 1000000;
              width: 42px;
              height: 42px;
              border-radius: 999px;
              border: 1px solid rgba(255, 255, 255, 0.7);
              background: rgba(15, 23, 42, 0.86);
              color: #ffffff;
              font-size: 28px;
              line-height: 38px;
              text-align: center;
              cursor: pointer;
              box-shadow: 0 10px 28px rgba(0, 0, 0, 0.34);
            }}
            #lashforge-fullscreen-close:hover {{
              background: rgba(239, 68, 68, 0.92);
            }}
            #lashforge-fullscreen-download {{
              position: fixed; top: 18px; right: 72px; z-index: 1000000;
              border: 1px solid rgba(255,255,255,.7); border-radius: 10px;
              background: #0f172a; color: white; padding: 11px 16px; cursor: pointer;
            }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer")) {{
          const overlay = hostDoc_{component_key}.createElement("div");
          overlay.id = "lashforge-fullscreen-viewer";
          overlay.innerHTML = '<button id="lashforge-fullscreen-download" type="button">下载原图</button><button id="lashforge-fullscreen-close" type="button" aria-label="关闭预览" title="关闭">×</button><img id="lashforge-fullscreen-image" src="" alt="preview" />';
          const activeDialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
          (activeDialog || hostDoc_{component_key}.body).appendChild(overlay);

          const state = {{
            scale: 1,
            offsetX: 0,
            offsetY: 0,
            dragging: false,
            dragStartX: 0,
            dragStartY: 0,
            dragOriginX: 0,
            dragOriginY: 0,
            pointerId: null,
          }};
          hostWindow_{component_key}.__lashforgeFullscreenState = state;

          const image = overlay.querySelector("img");
          const applyTransform = () => {{
            image.style.transform =
              "translate(" + state.offsetX + "px, " + state.offsetY + "px) scale(" + state.scale + ")";
          }};
          const resetTransform = () => {{
            state.scale = 1;
            state.offsetX = 0;
            state.offsetY = 0;
            state.dragging = false;
            image.classList.remove("dragging");
            applyTransform();
          }};
          const closeOverlay = () => {{
            // A captured pointer can otherwise keep the image as the active
            // target and make the close button/overlay appear unresponsive.
            if (state.pointerId !== null && image.releasePointerCapture) {{
              try {{ image.releasePointerCapture(state.pointerId); }} catch (e) {{}}
            }}
            overlay.classList.remove("active");
            resetTransform();
            state.pointerId = null;
          }};
          const closeButton = overlay.querySelector("#lashforge-fullscreen-close");
          if (closeButton) {{
            closeButton.addEventListener("pointerdown", (event) => {{
              event.preventDefault();
              event.stopPropagation();
              if (state.pointerId !== null && image.releasePointerCapture) {{
                try {{ image.releasePointerCapture(state.pointerId); }} catch (e) {{}}
              }}
              state.pointerId = null;
              state.dragging = false;
              image.classList.remove("dragging");
              closeOverlay();
            }});
            closeButton.addEventListener("click", (event) => {{
              event.preventDefault();
              event.stopPropagation();
              closeOverlay();
            }});
          }}

          overlay.addEventListener("click", (event) => {{
            if (event.target === overlay) {{
              closeOverlay();
            }}
          }});

          overlay.addEventListener("wheel", (event) => {{
            if (!overlay.classList.contains("active")) return;
            event.preventDefault();
            if (event.deltaY < 0) {{
              state.scale = Math.min(state.scale + 0.16, 6);
            }} else {{
              state.scale = Math.max(state.scale - 0.16, 0.35);
            }}
            applyTransform();
          }}, {{ passive: false }});

          image.addEventListener("pointerdown", (event) => {{
            if (!overlay.classList.contains("active")) return;
            if (event.button !== 0) return;
            event.preventDefault();
            state.dragging = true;
            state.dragStartX = event.clientX;
            state.dragStartY = event.clientY;
            state.dragOriginX = state.offsetX;
            state.dragOriginY = state.offsetY;
            state.pointerId = event.pointerId;
            image.classList.add("dragging");
            if (image.setPointerCapture) {{
              image.setPointerCapture(event.pointerId);
            }}
          }});

          image.addEventListener("pointermove", (event) => {{
            if (!state.dragging) return;
            event.preventDefault();
            state.offsetX = state.dragOriginX + (event.clientX - state.dragStartX);
            state.offsetY = state.dragOriginY + (event.clientY - state.dragStartY);
            applyTransform();
          }});

          const stopDragging = (event) => {{
            if (!state.dragging) return;
            state.dragging = false;
            image.classList.remove("dragging");
            if (event && image.releasePointerCapture) {{
              try {{
                image.releasePointerCapture(event.pointerId);
              }} catch (e) {{}}
            }}
          }};

          image.addEventListener("pointerup", stopDragging);
          image.addEventListener("pointercancel", stopDragging);
          image.addEventListener("lostpointercapture", () => {{
            state.dragging = false;
            image.classList.remove("dragging");
          }});

          hostDoc_{component_key}.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") {{
              closeOverlay();
            }}
          }});
        }}
        const activeOverlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        const activeImage = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        if (activeOverlay && activeImage) {{
          if (!hostWindow_{component_key}.__lashforgeFullscreenState) {{
            hostWindow_{component_key}.__lashforgeFullscreenState = {{
              scale: 1,
              offsetX: 0,
              offsetY: 0,
              dragging: false,
              dragStartX: 0,
              dragStartY: 0,
              dragOriginX: 0,
              dragOriginY: 0,
              pointerId: null,
            }};
          }}
          const resetActiveFullscreen = () => {{
            const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
            state.scale = 1;
            state.offsetX = 0;
            state.offsetY = 0;
            state.dragging = false;
            activeImage.classList.remove("dragging");
            activeImage.style.transform = "translate(0px, 0px) scale(1)";
          }};
          const closeActiveFullscreen = () => {{
            const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
            if (state.pointerId !== null && activeImage.releasePointerCapture) {{
              try {{ activeImage.releasePointerCapture(state.pointerId); }} catch (e) {{}}
            }}
            activeOverlay.classList.remove("active");
            resetActiveFullscreen();
            state.pointerId = null;
          }};
          hostWindow_{component_key}.__lashforgeCloseFullscreen = closeActiveFullscreen;
          const activeCloseButton = activeOverlay.querySelector("#lashforge-fullscreen-close");
          if (activeCloseButton) {{
            activeCloseButton.onpointerdown = (event) => {{
              event.preventDefault();
              event.stopPropagation();
              const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
              if (state.pointerId !== null && activeImage.releasePointerCapture) {{
                try {{ activeImage.releasePointerCapture(state.pointerId); }} catch (e) {{}}
              }}
              state.pointerId = null;
              state.dragging = false;
              activeImage.classList.remove("dragging");
              closeActiveFullscreen();
            }};
            activeCloseButton.onclick = (event) => {{
              event.preventDefault();
              event.stopPropagation();
              closeActiveFullscreen();
            }};
          }}
          activeOverlay.onclick = (event) => {{
            if (event.target === activeOverlay) {{
              closeActiveFullscreen();
            }}
          }};
          if (hostWindow_{component_key}.__lashforgeFullscreenKeyHandler) {{
            try {{
              hostDoc_{component_key}.removeEventListener("keydown", hostWindow_{component_key}.__lashforgeFullscreenKeyHandler, true);
            }} catch (e) {{}}
          }}
          hostWindow_{component_key}.__lashforgeFullscreenKeyHandler = (event) => {{
            if (event.key === "Escape" && activeOverlay.classList.contains("active")) {{
              event.preventDefault();
              event.stopImmediatePropagation();
              closeActiveFullscreen();
            }}
          }};
          hostDoc_{component_key}.addEventListener("keydown", hostWindow_{component_key}.__lashforgeFullscreenKeyHandler, true);
        }}
      }}

      function openFullscreen_{component_key}(src, index = 0) {{
        ensureOverlay_{component_key}();
        const previousMenu = hostDoc_{component_key}.getElementById("lashforge-eagle-menu");
        if (previousMenu) previousMenu.style.display = "none";
        const overlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        // Keep the viewer inside the active history dialog so its modal
        // backdrop and focus trap do not cover or disable the preview.
        let viewerHost = hostDoc_{component_key}.body;
        try {{
          const frame = window.frameElement;
          const dialog = frame && frame.closest('dialog, [role="dialog"]');
          if (dialog) viewerHost = dialog;
        }} catch (e) {{}}
        if (overlay.parentElement !== viewerHost) viewerHost.appendChild(overlay);
        // Modal managers can leave body-mounted UI inert after it is moved.
        // Only clear this component's owned nodes, never the page backdrop.
        overlay.inert = false;
        overlay.removeAttribute("inert");
        const image = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        const state = hostWindow_{component_key}.__lashforgeFullscreenState;
        image.src = normalizeViewerSrc_{component_key}(src);
        // Rebind the shared viewer on every open, including its originating
        // gallery and image index. Never retain the first card's download name.
        const downloadSrc = image.src;
        const downloadName = deriveEagleFileName_{component_key}(downloadSrc, index);
        image.oncontextmenu = (event) => {{
          if (!{allow_native_download}) {{ event.preventDefault(); return; }}
          // History originals use the browser menu so Copy Image also works
          // on HTTP pages without the JavaScript clipboard API.
          if ({native_fullscreen_menu} || event.altKey) return;
          event.preventDefault();
          openEagleMenu_{component_key}(event, downloadSrc, index);
        }};
        let downloadButton = overlay.querySelector("#lashforge-fullscreen-download");
        if (!downloadButton) {{
          downloadButton = hostDoc_{component_key}.createElement("button");
          downloadButton.id = "lashforge-fullscreen-download";
          downloadButton.type = "button";
          downloadButton.textContent = "下载原图";
          overlay.prepend(downloadButton);
        }}
        downloadButton.hidden = !{allow_native_download};
        downloadButton.onclick = () => downloadOriginal_{component_key}(downloadSrc, downloadName);
        state.scale = 1;
        state.offsetX = 0;
        state.offsetY = 0;
        state.dragging = false;
        image.classList.remove("dragging");
        image.style.transform = "translate(0px, 0px) scale(1)";
        overlay.classList.add("active");
      }}

      function buildDeleteUrl_{component_key}() {{
        const deleteToken = {delete_token};
        if (!deleteToken) return "";
        const currentUrl = new URL(hostWindow_{component_key}.location.href);
        currentUrl.searchParams.set("{UPLOAD_DELETE_QUERY_KEY}", deleteToken);
        return currentUrl.toString();
      }}

      images_{component_key}.forEach((item, index) => {{
        const wrap = document.createElement("div");
        wrap.className = "zoom-thumb-wrap";

        const img = document.createElement("img");
        img.src = item.src;
        img.className = "zoom-thumb";
        img.onclick = () => openFullscreen_{component_key}(item.full_src || item.src, index);
        img.oncontextmenu = (event) => {{
          if (!{allow_native_download}) {{
            event.preventDefault();
            showEagleToast_{component_key}("此处仅供预览，请使用页面上的 PSD 下载按钮");
            return;
          }}
          event.preventDefault();
          openEagleMenu_{component_key}(event, item.full_src || item.src, index);
        }};
        wrap.appendChild(img);

        if ({delete_token}) {{
          const deleteButton = document.createElement("button");
          deleteButton.type = "button";
          deleteButton.className = "zoom-thumb-delete";
          deleteButton.title = "删除当前图片";
          deleteButton.textContent = "×";
          deleteButton.addEventListener("pointerdown", (event) => {{
            event.stopPropagation();
          }});
          deleteButton.addEventListener("click", (event) => {{
            event.preventDefault();
            event.stopPropagation();
            const deleteUrl = buildDeleteUrl_{component_key}();
            if (deleteUrl) {{
              hostWindow_{component_key}.location.href = deleteUrl;
            }}
          }});
          wrap.appendChild(deleteButton);
        }}

        grid_{component_key}.appendChild(wrap);
      }});

    </script>
    """
    st.iframe(
        html_content,
        height="content",
        width="stretch",
    )


def render_before_after_compare_gallery(
    source_images,
    result_images,
    captions,
    feature_key,
    outpaint_alignments,
    download_images,
    *,
    Any,
    HISTORY_STATIC_ROUTE_PREFIX,
    JIMENG_UPLOAD_ROUTE_PREFIX,
    Path,
    REFERENCE_IMAGE_EXTENSIONS,
    build_direct_image_download_url,
    build_gallery_item,
    build_history_download_public_url,
    build_result_download_sources,
    components,
    get_history_public_base_url,
    get_jimeng_public_upload_base_url,
    json,
    os,
    re,
    render_result_preview_with_captions,
    urllib,
) -> None:
    normalized_download_images = list(download_images or build_result_download_sources(result_images))
    pairs: list[dict[str, Any]] = []
    for index, result_image in enumerate(result_images):
        source_image = source_images[index] if index < len(source_images) else ""
        if not source_image or not result_image:
            continue
        source_item = build_gallery_item(source_image, compress_preview=True, include_full_src=True)
        result_item = build_gallery_item(str(result_image), compress_preview=True, include_full_src=True)
        if not source_item or not result_item:
            continue
        result_full_source = (
            normalized_download_images[index]
            if index < len(normalized_download_images)
            else str(result_item.get("full_src") or result_image)
        )
        view_source = build_history_download_public_url(result_full_source)
        download_source = build_direct_image_download_url(view_source)
        download_path = Path(urllib.parse.unquote(urllib.parse.urlsplit(view_source).path or ""))
        download_extension = download_path.suffix if download_path.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS else ".png"
        download_name = download_path.name or f"扩图效果图_{index + 1}{download_extension}"
        pairs.append(
            {
                "source": source_item["src"],
                "result": result_item["src"],
                "view": view_source,
                "download": download_source,
                "download_name": download_name,
                "caption": str(captions[index] if index < len(captions) else f"结果 {index + 1}").strip(),
                "alignment": (
                    dict(outpaint_alignments[index] or {})
                    if outpaint_alignments and index < len(outpaint_alignments)
                    else {}
                ),
            }
        )
    if not pairs:
        render_result_preview_with_captions(
            result_images,
            captions,
            feature_key,
            download_images=normalized_download_images,
        )
        return
    component_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"compare_{feature_key}_{len(pairs)}")
    payload = json.dumps(pairs, ensure_ascii=False)
    managed_image_hosts = json.dumps(sorted({
        urllib.parse.urlsplit(base).hostname for base in
        (get_history_public_base_url(), get_jimeng_public_upload_base_url())
        if urllib.parse.urlsplit(base).hostname
    }))
    row_height = 672
    html_content = f"""
    <div id="{component_key}" class="compare-gallery-root"></div>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        color: #f5f7ff;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      .compare-gallery-root {{
        display: grid;
        gap: 16px;
        width: 100%;
        box-sizing: border-box;
      }}
      .compare-title {{
        color: rgba(214, 219, 255, 0.76);
        font-size: 12px;
        font-weight: 700;
        margin: 0 0 7px;
      }}
      .compare-pair {{
        display: block;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        overflow: hidden;
        background: rgba(7, 15, 31, 0.52);
        width: 100%;
        box-sizing: border-box;
      }}
      .compare-pane {{
        position: relative;
        height: 620px;
        background: rgba(4, 10, 24, 0.72);
        overflow: hidden;
        touch-action: none;
        box-sizing: border-box;
      }}
      .compare-stage {{
        cursor: ew-resize;
      }}
      .compare-canvas {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        display: block;
        z-index: 1;
      }}
      .compare-line {{
        position: absolute;
        top: 0;
        height: 100%;
        left: 50%;
        width: 2px;
        transform: translateX(-1px);
        background: #ffffff;
        box-shadow: 0 0 0 1px rgba(126, 96, 255, 0.78), 0 0 18px rgba(126, 96, 255, 0.72);
        pointer-events: none;
        z-index: 4;
      }}
      .compare-knob {{
        position: absolute;
        left: 50%;
        top: 50%;
        width: 30px;
        height: 30px;
        transform: translate(-50%, -50%);
        border-radius: 999px;
        background: rgba(126, 96, 255, 0.95);
        border: 2px solid rgba(255,255,255,0.9);
        pointer-events: none;
        z-index: 4;
      }}
      .compare-knob::before {{
        content: "↔";
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        font-size: 16px;
        font-weight: 800;
      }}
      .compare-slider {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: ew-resize;
        pointer-events: none;
        z-index: 6;
      }}
      .compare-native-result {{
        position: absolute;
        display: block;
        margin: 0;
        opacity: 1;
        object-fit: contain;
        cursor: zoom-in;
        user-select: none;
        -webkit-user-drag: none;
        z-index: 3;
      }}
      .compare-label {{
        position: absolute;
        top: 8px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(3, 8, 22, 0.7);
        color: rgba(245, 247, 255, 0.92);
        font-size: 11px;
        font-weight: 700;
        pointer-events: none;
        z-index: 5;
      }}
      .compare-label.left {{ left: 8px; }}
      .compare-label.right {{ right: 8px; }}
      .compare-download-hint {{
        position: absolute;
        right: 10px;
        bottom: 10px;
        padding: 5px 9px;
        border-radius: 999px;
        background: rgba(3, 8, 22, 0.72);
        color: rgba(245, 247, 255, 0.82);
        font-size: 11px;
        font-weight: 650;
        pointer-events: none;
        z-index: 5;
      }}
      @media (max-width: 720px) {{
        .compare-pane {{ height: 520px; }}
      }}
    </style>
    <script>
      const pairs_{component_key} = {payload};
      const root_{component_key} = document.getElementById("{component_key}");
      const hostWindow_{component_key} = (() => {{
        try {{
          return window.parent;
        }} catch (error) {{
          return window;
        }}
      }})();
      const hostDoc_{component_key} = (() => {{
        try {{
          return window.parent.document;
        }} catch (error) {{
          return document;
        }}
      }})();
      const normalizeNativeResultSrc_{component_key} = (src) => {{
        const raw = String(src || "").trim();
        if (!raw || raw.startsWith("data:")) return raw;
        try {{
          const parsed = new URL(raw, hostWindow_{component_key}.location.href);
          const isStaticImageRoute =
            (parsed.hostname === hostWindow_{component_key}.location.hostname || {managed_image_hosts}.includes(parsed.hostname)) &&
            (parsed.pathname.startsWith("{HISTORY_STATIC_ROUTE_PREFIX}/") ||
            parsed.pathname.startsWith("{JIMENG_UPLOAD_ROUTE_PREFIX}/"));
          if (!isStaticImageRoute) return parsed.toString();
          if ({json.dumps(os.getenv("TC_SINGLE_PORT") == "1")}) {{
            return new URL(parsed.pathname + parsed.search + parsed.hash,
              hostWindow_{component_key}.location.origin).toString();
          }}
          const currentProtocol = hostWindow_{component_key}.location.protocol || parsed.protocol;
          const currentHostname = hostWindow_{component_key}.location.hostname || parsed.hostname;
          const currentPort = parsed.port ? ":" + parsed.port : "";
          return `${{currentProtocol}}//${{currentHostname}}${{currentPort}}${{parsed.pathname}}${{parsed.search}}${{parsed.hash}}`;
        }} catch (error) {{
          return raw;
        }}
      }};
      const ensureCompareFullscreen_{component_key} = () => {{
        if (!hostDoc_{component_key}.getElementById("lashforge-fullscreen-style")) {{
          const style = hostDoc_{component_key}.createElement("style");
          style.id = "lashforge-fullscreen-style";
          style.textContent = `
            #lashforge-fullscreen-viewer {{
              position: fixed;
              inset: 0;
              z-index: 999999;
              background: rgba(3, 8, 22, 0.96);
              display: none;
              align-items: center;
              justify-content: center;
              overflow: hidden;
            }}
            #lashforge-fullscreen-viewer.active {{ display: flex; }}
            #lashforge-fullscreen-viewer img {{
              max-width: 96vw;
              max-height: 96vh;
              object-fit: contain;
              transform-origin: center center;
              transition: transform 0.08s linear;
              user-select: none;
              -webkit-user-drag: none;
              cursor: grab;
            }}
            #lashforge-fullscreen-viewer img.dragging {{ cursor: grabbing; }}
            #lashforge-fullscreen-close {{
              position: fixed;
              top: 18px;
              right: 18px;
              z-index: 1000000;
              width: 42px;
              height: 42px;
              border-radius: 999px;
              border: 1px solid rgba(255, 255, 255, 0.7);
              background: rgba(15, 23, 42, 0.86);
              color: #ffffff;
              font-size: 28px;
              line-height: 38px;
              text-align: center;
              cursor: pointer;
              box-shadow: 0 10px 28px rgba(0, 0, 0, 0.34);
            }}
            #lashforge-fullscreen-close:hover {{ background: rgba(239, 68, 68, 0.92); }}
          `;
          hostDoc_{component_key}.head.appendChild(style);
        }}
        let overlay = hostDoc_{component_key}.getElementById("lashforge-fullscreen-viewer");
        if (overlay) return overlay;
        overlay = hostDoc_{component_key}.createElement("div");
        overlay.id = "lashforge-fullscreen-viewer";
        overlay.innerHTML = '<button id="lashforge-fullscreen-close" type="button" aria-label="关闭预览" title="关闭">×</button><img id="lashforge-fullscreen-image" src="" alt="preview" />';
        const activeDialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
        (activeDialog || hostDoc_{component_key}.body).appendChild(overlay);
        const state = {{
          scale: 1,
          offsetX: 0,
          offsetY: 0,
          dragging: false,
          dragStartX: 0,
          dragStartY: 0,
          dragOriginX: 0,
          dragOriginY: 0,
          pointerId: null,
        }};
        hostWindow_{component_key}.__lashforgeFullscreenState = state;
        const image = overlay.querySelector("img");
        const applyTransform = () => {{
          image.style.transform =
            "translate(" + state.offsetX + "px, " + state.offsetY + "px) scale(" + state.scale + ")";
        }};
        const resetTransform = () => {{
          state.scale = 1;
          state.offsetX = 0;
          state.offsetY = 0;
          state.dragging = false;
          image.classList.remove("dragging");
          applyTransform();
        }};
        const closeOverlay = () => {{
          if (state.pointerId !== null && image.releasePointerCapture) {{
            try {{ image.releasePointerCapture(state.pointerId); }} catch (e) {{}}
          }}
          overlay.classList.remove("active");
          resetTransform();
          state.pointerId = null;
        }};
        hostWindow_{component_key}.__lashforgeCloseFullscreen = closeOverlay;
        overlay.querySelector("#lashforge-fullscreen-close").onpointerdown = (event) => {{
          event.preventDefault();
          event.stopPropagation();
          if (state.pointerId !== null && image.releasePointerCapture) {{
            try {{ image.releasePointerCapture(state.pointerId); }} catch (e) {{}}
          }}
          state.pointerId = null;
          state.dragging = false;
          image.classList.remove("dragging");
          closeOverlay();
        }};
        overlay.querySelector("#lashforge-fullscreen-close").addEventListener("click", (event) => {{
          event.preventDefault();
          event.stopPropagation();
          closeOverlay();
        }});
        overlay.addEventListener("click", (event) => {{
          if (event.target === overlay) closeOverlay();
        }});
        overlay.addEventListener("wheel", (event) => {{
          if (!overlay.classList.contains("active")) return;
          event.preventDefault();
          state.scale = event.deltaY < 0
            ? Math.min(state.scale + 0.16, 6)
            : Math.max(state.scale - 0.16, 0.35);
          applyTransform();
        }}, {{ passive: false }});
        image.addEventListener("pointerdown", (event) => {{
          if (!overlay.classList.contains("active") || event.button !== 0) return;
          event.preventDefault();
          state.dragging = true;
          state.dragStartX = event.clientX;
          state.dragStartY = event.clientY;
          state.dragOriginX = state.offsetX;
          state.dragOriginY = state.offsetY;
          state.pointerId = event.pointerId;
          image.classList.add("dragging");
          image.setPointerCapture && image.setPointerCapture(event.pointerId);
        }});
        image.addEventListener("pointermove", (event) => {{
          if (!state.dragging) return;
          event.preventDefault();
          state.offsetX = state.dragOriginX + (event.clientX - state.dragStartX);
          state.offsetY = state.dragOriginY + (event.clientY - state.dragStartY);
          applyTransform();
        }});
        const stopImageDrag = () => {{
          state.dragging = false;
          image.classList.remove("dragging");
        }};
        image.addEventListener("pointerup", stopImageDrag);
        image.addEventListener("pointercancel", stopImageDrag);
        image.addEventListener("lostpointercapture", stopImageDrag);
        if (hostWindow_{component_key}.__lashforgeFullscreenKeyHandler) {{
          try {{
            hostDoc_{component_key}.removeEventListener(
              "keydown",
              hostWindow_{component_key}.__lashforgeFullscreenKeyHandler,
              true
            );
          }} catch (error) {{}}
        }}
        hostWindow_{component_key}.__lashforgeFullscreenKeyHandler = (event) => {{
          if (event.key === "Escape") closeOverlay();
        }};
        hostDoc_{component_key}.addEventListener(
          "keydown",
          hostWindow_{component_key}.__lashforgeFullscreenKeyHandler,
          true
        );
        return overlay;
      }};
      const openCompareFullscreen_{component_key} = (src) => {{
        const overlay = ensureCompareFullscreen_{component_key}();
        const dialog = window.frameElement && window.frameElement.closest('dialog, [role="dialog"]');
        const viewerHost = dialog || hostDoc_{component_key}.body;
        if (overlay.parentElement !== viewerHost) viewerHost.appendChild(overlay);
        overlay.inert = false;
        overlay.removeAttribute("inert");
        const previousMenu = hostDoc_{component_key}.getElementById("lashforge-eagle-menu");
        if (previousMenu) previousMenu.style.display = "none";
        const image = hostDoc_{component_key}.getElementById("lashforge-fullscreen-image");
        const state = hostWindow_{component_key}.__lashforgeFullscreenState || {{}};
        state.scale = 1;
        state.offsetX = 0;
        state.offsetY = 0;
        state.dragging = false;
        hostWindow_{component_key}.__lashforgeFullscreenState = state;
        image.src = normalizeNativeResultSrc_{component_key}(src);
        // The viewer is shared with history/results. Clear their stale image
        // handler and bind this comparison's untouched original on every open.
        image.oncontextmenu = null;
        const currentSrc = image.src;
        const currentPair = pairs_{component_key}.find(pair => (pair.view || pair.result) === src) || {{}};
        const downloadName = currentPair.download_name || "original.png";
        let downloadButton = overlay.querySelector("#lashforge-fullscreen-download");
        if (!downloadButton) {{
          downloadButton = hostDoc_{component_key}.createElement("button");
          downloadButton.id = "lashforge-fullscreen-download";
          downloadButton.type = "button";
          overlay.prepend(downloadButton);
        }}
        downloadButton.textContent = "下载原图";
        downloadButton.hidden = false;
        downloadButton.style.cssText = "position:fixed;top:18px;right:72px;z-index:1000000;border:1px solid #94a3b8;border-radius:10px;background:#0f172a;color:white;padding:11px 16px;cursor:pointer";
        downloadButton.onclick = () => {{
          const url = new URL(currentSrc, hostWindow_{component_key}.location.href);
          if (url.protocol === "http:" || url.protocol === "https:") {{
            url.searchParams.set("download", "1");
            url.searchParams.set("filename", downloadName);
          }}
          const link = hostDoc_{component_key}.createElement("a");
          link.href = url.toString();
          link.download = downloadName;
          overlay.appendChild(link);
          link.click();
          link.remove();
        }};
        image.classList.remove("dragging");
        image.style.transform = "translate(0px, 0px) scale(1)";
        overlay.classList.add("active");
      }};
      pairs_{component_key}.forEach((pair, index) => {{
        const wrap = document.createElement("div");
        const title = document.createElement("div");
        title.className = "compare-title";
        title.textContent = pair.caption || `结果 ${{index + 1}}`;
        const grid = document.createElement("div");
        grid.className = "compare-pair";
        grid.innerHTML = `
          <div class="compare-pane compare-control compare-stage">
            <canvas class="compare-canvas"></canvas>
            <span class="compare-label left">原图</span>
            <span class="compare-label right">效果图</span>
            <span class="compare-download-hint">左键查看大图 · 右键使用 Chrome 原生菜单</span>
            <div class="compare-line"></div>
            <div class="compare-knob"></div>
            <input class="compare-slider" type="range" min="0" max="100" value="50" aria-label="对比滑块">
            <img class="compare-native-result" alt="效果图原图" draggable="false">
          </div>`;
        wrap.appendChild(title);
        wrap.appendChild(grid);
        root_{component_key}.appendChild(wrap);
        const control = grid.querySelector(".compare-control");
        const canvas = control.querySelector(".compare-canvas");
        const ctx = canvas.getContext("2d");
        const slider = control.querySelector(".compare-slider");
        const line = control.querySelector(".compare-line");
        const knob = control.querySelector(".compare-knob");
        const nativeResultImage = control.querySelector(".compare-native-result");
        const sourceImage = new Image();
        const resultImage = new Image();
        let currentValue = 50;
        let drawBox = {{ x: 0, y: 0, width: 1, height: 1 }};
        const getContainBox = (image, stageWidth, stageHeight) => {{
          const naturalWidth = Math.max(image.naturalWidth || 1, 1);
          const naturalHeight = Math.max(image.naturalHeight || 1, 1);
          const imageRatio = naturalWidth / naturalHeight;
          let width = stageWidth;
          let height = width / imageRatio;
          if (height > stageHeight) {{
            height = stageHeight;
            width = height * imageRatio;
          }}
          return {{
            x: (stageWidth - width) / 2,
            y: (stageHeight - height) / 2,
            width,
            height,
          }};
        }};
        const drawImageContain = (image, box) => {{
          ctx.drawImage(image, box.x, box.y, box.width, box.height);
        }};
        const renderCanvas = () => {{
          const stageWidth = Math.max(control.clientWidth, 1);
          const stageHeight = Math.max(control.clientHeight, 1);
          const dpr = Math.max(window.devicePixelRatio || 1, 1);
          const pixelWidth = Math.round(stageWidth * dpr);
          const pixelHeight = Math.round(stageHeight * dpr);
          if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {{
            canvas.width = pixelWidth;
            canvas.height = pixelHeight;
          }}
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          ctx.clearRect(0, 0, stageWidth, stageHeight);
          const sourceReady = sourceImage.complete && sourceImage.naturalWidth > 0;
          const resultReady = resultImage.complete && resultImage.naturalWidth > 0;
          if (!sourceReady || !resultReady) {{
            return;
          }}
          drawBox = getContainBox(resultImage, stageWidth, stageHeight);
          drawImageContain(resultImage, drawBox);
          const revealWidth = drawBox.width * currentValue / 100;
          const alignment = pair.alignment || {{}};
          const targetWidth = Number(alignment.target_width || 0);
          const targetHeight = Number(alignment.target_height || 0);
          const sourceWidth = Number(alignment.source_width || 0);
          const sourceHeight = Number(alignment.source_height || 0);
          const hasAlignment = targetWidth > 0 && targetHeight > 0 && sourceWidth > 0 && sourceHeight > 0;
          ctx.save();
          ctx.beginPath();
          ctx.rect(drawBox.x, drawBox.y, revealWidth, drawBox.height);
          ctx.clip();
          if (hasAlignment) {{
            ctx.fillStyle = "rgba(4, 10, 24, 0.98)";
            ctx.fillRect(drawBox.x, drawBox.y, drawBox.width, drawBox.height);
            const sourceBox = {{
              x: drawBox.x + (Number(alignment.left || 0) / targetWidth) * drawBox.width,
              y: drawBox.y + (Number(alignment.top || 0) / targetHeight) * drawBox.height,
              width: (sourceWidth / targetWidth) * drawBox.width,
              height: (sourceHeight / targetHeight) * drawBox.height,
            }};
            drawImageContain(sourceImage, sourceBox);
          }} else {{
            const sourceBox = getContainBox(sourceImage, stageWidth, stageHeight);
            drawImageContain(sourceImage, sourceBox);
          }}
          ctx.restore();
          const lineLeft = drawBox.x + drawBox.width * currentValue / 100;
          line.style.left = `${{lineLeft}}px`;
          line.style.top = `${{drawBox.y}}px`;
          line.style.height = `${{drawBox.height}}px`;
          knob.style.left = `${{lineLeft}}px`;
          knob.style.top = `${{drawBox.y + drawBox.height / 2}}px`;
          nativeResultImage.style.left = `${{drawBox.x}}px`;
          nativeResultImage.style.top = `${{drawBox.y}}px`;
          nativeResultImage.style.width = `${{drawBox.width}}px`;
          nativeResultImage.style.height = `${{drawBox.height}}px`;
          nativeResultImage.style.clipPath = `inset(0 0 0 ${{currentValue}}%)`;
        }};
        const update = (nextValue) => {{
          const value = Math.max(0, Math.min(100, Number(nextValue ?? slider.value ?? 50)));
          currentValue = value;
          slider.value = String(value);
          renderCanvas();
        }};
        const updateFromPointer = (event) => {{
          const rect = control.getBoundingClientRect();
          const clientX = event.touches && event.touches.length ? event.touches[0].clientX : event.clientX;
          const localX = clientX - rect.left;
          const boxStart = drawBox.x;
          const boxWidth = Math.max(drawBox.width, 1);
          update(((localX - boxStart) / boxWidth) * 100);
        }};
        let dragging = false;
        let dragMoved = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let pointerDownOnEffect = false;
        control.addEventListener("pointerdown", (event) => {{
          if (event.button !== 0) return;
          dragging = true;
          dragMoved = false;
          dragStartX = event.clientX;
          dragStartY = event.clientY;
          pointerDownOnEffect = event.target === nativeResultImage;
          control.setPointerCapture && control.setPointerCapture(event.pointerId);
          if (!pointerDownOnEffect) updateFromPointer(event);
        }});
        control.addEventListener("pointermove", (event) => {{
          if (!dragging) return;
          if (Math.hypot(event.clientX - dragStartX, event.clientY - dragStartY) > 5) {{
            dragMoved = true;
          }}
          if (!dragMoved && pointerDownOnEffect) return;
          updateFromPointer(event);
        }});
        const stopDrag = () => {{ dragging = false; }};
        control.addEventListener("pointerup", stopDrag);
        control.addEventListener("pointercancel", () => {{
          dragging = false;
          pointerDownOnEffect = false;
          dragMoved = false;
        }});
        control.addEventListener("lostpointercapture", stopDrag);
        control.addEventListener("click", (event) => {{
          const shouldOpen = pointerDownOnEffect && !dragMoved;
          pointerDownOnEffect = false;
          dragMoved = false;
          if (!shouldOpen) return;
          event.preventDefault();
          event.stopPropagation();
          openCompareFullscreen_{component_key}(pair.view || pair.result);
        }});
        slider.addEventListener("input", () => update(slider.value));
        window.addEventListener("resize", () => update(slider.value));
        sourceImage.addEventListener("load", () => update(currentValue));
        resultImage.addEventListener("load", () => update(currentValue));
        nativeResultImage.addEventListener("dragstart", (event) => event.preventDefault());
        sourceImage.src = pair.source;
        resultImage.src = pair.result;
        nativeResultImage.src = normalizeNativeResultSrc_{component_key}(pair.view || pair.result);
        update(50);
      }});
    </script>
    """
    components.html(html_content, height=max(len(pairs), 1) * row_height, scrolling=False)
