import { isAPlusWorkspace } from "@/lib/canvas/workspace";
import { imageToDataUrl } from "@/services/image-storage";
import type { CanvasModelHdMethod, CanvasXiaohaImageFeature } from "@/types/canvas";
import type { ReferenceImage } from "@/types/image";

export const DEFAULT_MODEL_HD_METHOD: CanvasModelHdMethod = "nano-banana-2";
export const MODEL_HD_METHOD_OPTIONS: Array<{ value: CanvasModelHdMethod; label: string }> = [
    { value: "nano-banana-2", label: "Nano Banana 2.1 · 模特高清" },
    { value: "seedream-5-pro", label: "即梦 5 Pro · 模特高清" },
];
export const IMAGE_PROCESSING_MODEL_OPTIONS: Array<{ value: CanvasModelHdMethod; label: string }> = [
    { value: "nano-banana-2", label: "Nano Banana 2.1" },
    { value: "seedream-5-pro", label: "即梦 5 Pro" },
];

export type XiaohaImageFeatureOption = {
    value: CanvasXiaohaImageFeature;
    label: string;
    requiresReference?: boolean;
    promptRequired?: boolean;
    fixedEngine?: boolean;
};

export const A_PLUS_IMAGE_FEATURE_OPTIONS: XiaohaImageFeatureOption[] = [
    { value: "reference_reverse", label: "参考图反推", fixedEngine: true },
    { value: "reference_compose", label: "文案组合生图", fixedEngine: true },
    { value: "main_image_a_plus", label: "主图生A+", fixedEngine: true },
    { value: "a_plus_reference_lab", label: "A+版式参考实验室", fixedEngine: true },
    { value: "a_plus_style_model_replace", label: "A+首屏风格复刻—替换模特", fixedEngine: true, requiresReference: true },
    { value: "a_plus_first_screen_selling_points", label: "首屏+卖点融合", fixedEngine: true, requiresReference: true },
    { value: "amazon_to_walmart_a_plus", label: "亚马逊A+改沃尔玛A+", fixedEngine: true },
    { value: "a_plus_hero_style_reverse", label: "A+首屏风格反推", fixedEngine: true },
    { value: "amazon_a_plus", label: "自由创作PSD", fixedEngine: true },
];
export const isAPlusFeature = (value: string) => A_PLUS_IMAGE_FEATURE_OPTIONS.some((item) => item.value === value);

export const DEFAULT_XIAOHA_IMAGE_FEATURE: CanvasXiaohaImageFeature = isAPlusWorkspace ? "main_image_a_plus" : "modelHd";
export const XIAOHA_IMAGE_FEATURE_OPTIONS: XiaohaImageFeatureOption[] = [
    ...A_PLUS_IMAGE_FEATURE_OPTIONS,
    { value: "product_retouch", label: "产品图精修 · Nano Banana 2.1", fixedEngine: true, requiresReference: true },
    { value: "product_retouch_local", label: "局部瑕疵修复 · Nano Banana 2.1", fixedEngine: true, promptRequired: true },
    { value: "modelHd", label: "模特高清" },
    { value: "jimeng_hd_upscale", label: "即梦超清 8K", fixedEngine: true },
    { value: "background_cutout", label: "智能抠图", fixedEngine: true },
    { value: "remove_eyelashes", label: "批量去掉睫毛" },
    { value: "pose_change", label: "模特换姿势", requiresReference: true },
    { value: "scene_change", label: "模特换场景", requiresReference: true },
    { value: "outpaint", label: "模特扩图" },
    { value: "single_to_double", label: "单眼变双眼" },
    { value: "skin_tone", label: "模特换肤色", requiresReference: true },
    { value: "pupil_color_change", label: "换瞳孔颜色", requiresReference: true },
    { value: "eye_shape_change", label: "换眼型", requiresReference: true },
    { value: "three_view", label: "模特侧面图生成", requiresReference: true },
    { value: "ai_qa_image", label: "AI问答生图", promptRequired: true },
];

export const workspaceImageFeatureOptions = isAPlusWorkspace ? A_PLUS_IMAGE_FEATURE_OPTIONS : XIAOHA_IMAGE_FEATURE_OPTIONS;

export function getXiaohaImageFeatureOption(value: CanvasXiaohaImageFeature) {
    return XIAOHA_IMAGE_FEATURE_OPTIONS.find((option) => option.value === value) || XIAOHA_IMAGE_FEATURE_OPTIONS[0];
}

type ModelHdResponse = {
    success?: boolean;
    image?: string;
    images?: string[];
    psdUrl?: string;
    message?: string;
    featureName?: string;
    channel?: string;
};

export type XiaohaOutpaintSettings = { top: number; bottom: number; left: number; right: number };

export async function requestPublicFigureDetection(images: string[], signal?: AbortSignal) {
    if (!images.length) return { detected: false, names: [] as string[] };
    const response = await fetch(xiaohaApiUrl("detect-public-figures"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ images }),
        signal,
    });
    const payload = (await response.json().catch(() => ({}))) as { success?: boolean; message?: string; detected?: boolean; names?: string[] };
    if (!response.ok || !payload.success) {
        throw new Error(payload.message || `公众人物检测失败（HTTP ${response.status}）`);
    }
    return { detected: Boolean(payload.detected), names: Array.isArray(payload.names) ? payload.names : [] };
}

export async function requestXiaohaModelHd(reference: ReferenceImage, prompt = "", signal?: AbortSignal, method: CanvasModelHdMethod = DEFAULT_MODEL_HD_METHOD) {
    const image = await imageToDataUrl({ dataUrl: reference.dataUrl, storageKey: reference.storageKey });
    if (!image) throw new Error("无法读取模特高清原图");

    const response = await fetch(xiaohaApiUrl("model-hd"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ image, prompt: prompt.trim(), method }),
        signal,
    });
    const payload = (await response.json().catch(() => ({}))) as ModelHdResponse;
    if (!response.ok || !payload.success || !payload.image) {
        throw new Error(payload.message || `模特高清请求失败（HTTP ${response.status}）`);
    }
    return payload.image;
}

export async function requestXiaohaImageFeature(
    references: ReferenceImage[],
    feature: CanvasXiaohaImageFeature,
    prompt = "",
    signal?: AbortSignal,
    method: CanvasModelHdMethod = DEFAULT_MODEL_HD_METHOD,
    outpaint?: XiaohaOutpaintSettings,
) {
    const source = references[0];
    if (!source) throw new Error("请先提供 1 张待处理原图");
    if (feature === "modelHd") return requestXiaohaModelHd(source, prompt, signal, method);

    const images = await Promise.all(
        references.map(async (reference) => {
            const image = await imageToDataUrl({ dataUrl: reference.dataUrl, storageKey: reference.storageKey });
            if (!image) throw new Error(`无法读取图片：${reference.name || reference.id}`);
            return image;
        }),
    );
    const response = await fetch(xiaohaApiUrl("image-feature"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ feature, images, prompt: prompt.trim(), method, outpaint }),
        signal,
    });
    const payload = (await response.json().catch(() => ({}))) as ModelHdResponse;
    if (!response.ok || !payload.success || !payload.image) {
        throw new Error(payload.message || `图片功能请求失败（HTTP ${response.status}）`);
    }
    return payload.image;
}

export async function requestXiaohaAPlusFeature(references: ReferenceImage[], feature: CanvasXiaohaImageFeature, prompt: string, signal?: AbortSignal) {
    const images = await Promise.all(references.map((reference) => imageToDataUrl({ dataUrl: reference.dataUrl, storageKey: reference.storageKey })));
    if (!images.length || images.some((image) => !image)) throw new Error("请连接可读取的A+素材图片");
    const response = await fetch(xiaohaApiUrl("image-feature"), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ feature, images, prompt: prompt.trim() }), signal,
    });
    const payload = (await response.json().catch(() => ({}))) as ModelHdResponse;
    if (!response.ok || !payload.success || !payload.images?.length) throw new Error(payload.message || `A+处理失败（HTTP ${response.status}）`);
    return { images: payload.images, psdUrl: payload.psdUrl };
}

export async function requestXiaohaReferenceNode(action: "analyze" | "generate", references: ReferenceImage[], prompt: string, signal?: AbortSignal) {
    const images = await Promise.all(references.map((ref) => imageToDataUrl({ dataUrl: ref.dataUrl, storageKey: ref.storageKey })));
    if (images.some((image) => !image)) throw new Error("无法读取参考图");
    const response = await fetch(xiaohaApiUrl("reference-node"), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ action, images, prompt }), signal,
    });
    const payload = await response.json() as { success?: boolean; message?: string; text?: string; analysis?: Record<string, string>; images?: string[] };
    if (!response.ok || !payload.success) throw new Error(payload.message || `参考节点处理失败（HTTP ${response.status}）`);
    if (action === "analyze" && (!payload.text || !payload.analysis)) throw new Error("未返回完整逆向文案");
    if (action === "generate" && !payload.images?.length) throw new Error("未返回生成结果");
    return payload;
}

export async function recordCanvasImageUsage(action: "image_generation" | "image_edit" | "image_generation_retry" | "image_edit_retry", model: string, imageCount: number) {
    try {
        const response = await fetch(xiaohaApiUrl("usage-record"), {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ action, model: model.trim(), imageCount }),
        });
        if (!response.ok) console.warn(`无限画布使用记录写入失败（HTTP ${response.status}）`);
    } catch (error) {
        console.warn("无限画布使用记录写入失败", error);
    }
}

function xiaohaApiUrl(endpoint: string) {
    const basePath = import.meta.env.BASE_URL.endsWith("/") ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
    const pageParams = new URLSearchParams(window.location.search);
    const authParams = new URLSearchParams();
    const authUser = pageParams.get("auth_user");
    const authToken = pageParams.get("auth_token");
    if (authUser) authParams.set("auth_user", authUser);
    if (authToken) authParams.set("auth_token", authToken);
    return `${basePath}api/${endpoint}${authParams.size ? `?${authParams.toString()}` : ""}`;
}
