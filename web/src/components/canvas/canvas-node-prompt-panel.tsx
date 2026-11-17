import { useEffect, useState } from "react";
import { ArrowUp, LoaderCircle, Settings2, Square } from "lucide-react";
import { Button, InputNumber, Popover, Select } from "antd";

import { ModelPicker } from "@/components/model-picker";
import {
    DEFAULT_MODEL_HD_METHOD,
    DEFAULT_XIAOHA_IMAGE_FEATURE,
    getXiaohaImageFeatureOption,
    IMAGE_PROCESSING_MODEL_OPTIONS,
    MODEL_HD_METHOD_OPTIONS,
    XIAOHA_IMAGE_FEATURE_OPTIONS,
} from "@/services/api/xiaoha";
import { defaultConfig, modelAvailableForCapability, useConfigStore, useEffectiveConfig, type AiConfig } from "@/stores/use-config-store";
import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";
import { CanvasPromptLibrary } from "./canvas-prompt-library";
import { CanvasAudioSettingsPopover, type CanvasAudioSettingKey } from "./canvas-audio-settings-popover";
import { CanvasResourceMentionTextarea } from "./canvas-resource-mention-textarea";
import { CanvasVideoSettingsPopover } from "./canvas-video-settings-popover";
import { CanvasNodeType, type CanvasGenerationMode, type CanvasModelHdMethod, type CanvasNodeData, type CanvasXiaohaImageFeature } from "@/types/canvas";
import type { CanvasResourceReference } from "@/lib/canvas/canvas-resource-references";

export type CanvasNodeGenerationMode = CanvasGenerationMode;

type CanvasNodePromptPanelProps = {
    node: CanvasNodeData;
    isRunning: boolean;
    onPromptChange: (nodeId: string, prompt: string) => void;
    onConfigChange: (nodeId: string, patch: Partial<CanvasNodeData["metadata"]>) => void;
    onGenerate: (nodeId: string, mode: CanvasNodeGenerationMode, prompt: string) => void;
    onStop: (nodeId: string) => void;
    mentionReferences?: CanvasResourceReference[];
    onImageSettingsOpenChange?: (open: boolean) => void;
};

export function CanvasNodePromptPanel({ node, isRunning, onPromptChange, onConfigChange, onGenerate, onStop, mentionReferences = [] }: CanvasNodePromptPanelProps) {
    const globalConfig = useEffectiveConfig();
    const openConfigDialog = useConfigStore((state) => state.openConfigDialog);
    const theme = canvasThemes[useThemeStore((state) => state.theme)];
    const mode = defaultMode(node.type);
    const config = buildNodeConfig(globalConfig, node, mode);
    const hasTextContent = node.type === CanvasNodeType.Text && Boolean(node.metadata?.content?.trim());
    const hasImageContent = node.type === CanvasNodeType.Image && Boolean(node.metadata?.content);
    const isXiaohaImage = mode === "image";
    const imageFeature: CanvasXiaohaImageFeature =
        node.metadata?.imageFunction && node.metadata.imageFunction !== "generate"
            ? node.metadata.imageFunction
            : DEFAULT_XIAOHA_IMAGE_FEATURE;
    const imageFeatureOption = getXiaohaImageFeatureOption(imageFeature);
    const isModelHd = imageFeature === "modelHd";
    const modelHdMethod = node.metadata?.modelHdMethod || DEFAULT_MODEL_HD_METHOD;
    const connectedImageCount = mentionReferences.filter((reference) => reference.kind === "image" && reference.nodeId !== node.id).length;
    const hasRequiredReference = !imageFeatureOption.requiresReference || connectedImageCount > 0;
    const outpaintTotal =
        Number(node.metadata?.outpaintTop ?? 100) +
        Number(node.metadata?.outpaintBottom ?? 100) +
        Number(node.metadata?.outpaintLeft ?? 100) +
        Number(node.metadata?.outpaintRight ?? 100);
    const isEditingExistingContent = hasTextContent || hasImageContent;
    const [prompt, setPrompt] = useState(isEditingExistingContent ? "" : node.metadata?.prompt || "");

    useEffect(() => {
        setPrompt(isEditingExistingContent ? "" : node.metadata?.prompt || "");
    }, [isEditingExistingContent, node.id]);

    const updatePrompt = (value: string) => {
        setPrompt(value);
        if (!isEditingExistingContent) onPromptChange(node.id, value);
    };

    const submit = () => {
        const text = prompt.trim();
        if (
            isRunning ||
            (isXiaohaImage && (!hasImageContent || !hasRequiredReference || (imageFeatureOption.promptRequired && !text) || (imageFeature === "outpaint" && outpaintTotal <= 0))) ||
            (!isXiaohaImage && !text)
        ) return;
        onGenerate(node.id, mode, text);
        setPrompt("");
    };
    const canSubmit = isXiaohaImage
        ? hasImageContent && hasRequiredReference && (!imageFeatureOption.promptRequired || Boolean(prompt.trim())) && (imageFeature !== "outpaint" || outpaintTotal > 0)
        : Boolean(prompt.trim());

    return (
        <div
            className="rounded-2xl border p-3 shadow-2xl backdrop-blur"
            style={{ background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.node.text }}
            onMouseDown={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
            onWheel={(event) => event.stopPropagation()}
        >
            {isXiaohaImage ? (
                <div className="mb-2 flex min-w-0 items-center gap-2">
                    <Select
                        className="min-w-0 flex-1"
                        value={imageFeature}
                        options={XIAOHA_IMAGE_FEATURE_OPTIONS.map((option) => ({
                            value: option.value,
                            label: `${option.label}${option.requiresReference ? " · 需参考图" : ""}`,
                        }))}
                        popupMatchSelectWidth={240}
                        onChange={(value) => onConfigChange(node.id, { imageFunction: value as CanvasXiaohaImageFeature })}
                    />
                    {!imageFeatureOption.fixedEngine ? (
                        <ModelPicker
                            className="min-w-0 flex-1"
                            config={config}
                            value={modelHdMethod}
                            models={IMAGE_PROCESSING_MODEL_OPTIONS.map((option) => option.value)}
                            modelLabels={Object.fromEntries(
                                (isModelHd ? MODEL_HD_METHOD_OPTIONS : IMAGE_PROCESSING_MODEL_OPTIONS).map((option) => [option.value, option.label]),
                            )}
                            onChange={(method) => onConfigChange(node.id, { modelHdMethod: method as CanvasModelHdMethod })}
                        />
                    ) : null}
                    {imageFeature === "outpaint" ? <OutpaintSettingsButton node={node} onConfigChange={onConfigChange} /> : null}
                </div>
            ) : null}

            <CanvasResourceMentionTextarea
                value={prompt}
                references={mentionReferences}
                onChange={updatePrompt}
                onSubmit={submit}
                className="thin-scrollbar h-24 w-full resize-none rounded-xl border px-3 py-2 text-sm leading-5 outline-none"
                style={{ background: theme.node.fill, borderColor: theme.node.stroke, color: theme.node.text }}
                placeholder={promptPlaceholder(mode, hasImageContent, hasTextContent, imageFeature, imageFeatureOption.label, hasRequiredReference)}
            />

            <div className="mt-2 flex min-w-0 items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                    {!isXiaohaImage ? <CanvasPromptLibrary onSelect={updatePrompt} /> : (
                        <span className="truncate text-xs opacity-60">{hasRequiredReference ? imageFeatureOption.label : "请先连接参考图"}</span>
                    )}
                    {mode === "video" ? (
                        <>
                            <ModelPicker config={config} value={config.model} onChange={(model) => onConfigChange(node.id, { model })} capability="video" onMissingConfig={() => openConfigDialog(true)} />
                            <CanvasVideoSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-full !px-3" onConfigChange={(key, value) => onConfigChange(node.id, videoConfigPatch(key, value))} />
                        </>
                    ) : mode === "audio" ? (
                        <>
                            <ModelPicker config={config} value={config.model} onChange={(model) => onConfigChange(node.id, { model })} capability="audio" onMissingConfig={() => openConfigDialog(true)} />
                            <CanvasAudioSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-full !px-3" onConfigChange={(key, value) => onConfigChange(node.id, audioConfigPatch(key, value))} />
                        </>
                    ) : (
                        <ModelPicker config={config} value={config.model} onChange={(model) => onConfigChange(node.id, { model })} capability="text" onMissingConfig={() => openConfigDialog(true)} />
                    )}
                </div>
                <Button
                    type="primary"
                    className="!h-10 !min-w-16 shrink-0 !rounded-full !px-3"
                    danger={isRunning}
                    disabled={!isRunning && !canSubmit}
                    onClick={() => (isRunning ? onStop(node.id) : submit())}
                    aria-label={isRunning ? "停止生成" : "生成"}
                >
                    <span className="flex items-center gap-1.5">
                        {isRunning ? (
                            <>
                                <LoaderCircle className="size-4 animate-spin" />
                                <Square className="size-3.5 fill-current" />
                                <span className="text-xs font-medium">停止</span>
                            </>
                        ) : (
                            <ArrowUp className="size-4" />
                        )}
                    </span>
                </Button>
            </div>
        </div>
    );
}

function defaultMode(type: CanvasNodeData["type"]): CanvasNodeGenerationMode {
    return type === CanvasNodeType.Text ? "text" : type === CanvasNodeType.Video ? "video" : type === CanvasNodeType.Audio ? "audio" : "image";
}

function buildNodeConfig(globalConfig: AiConfig, node: CanvasNodeData, mode: CanvasNodeGenerationMode): AiConfig {
    const defaultModel = mode === "image" ? globalConfig.imageModel : mode === "video" ? globalConfig.videoModel : mode === "audio" ? globalConfig.audioModel : globalConfig.textModel;
    const fallbackModel = mode === "image" ? defaultConfig.imageModel : mode === "video" ? defaultConfig.videoModel : mode === "audio" ? defaultConfig.audioModel : defaultConfig.textModel;
    const currentModel = node.metadata?.model;
    const model = currentModel && modelAvailableForCapability(globalConfig, currentModel, mode)
        ? currentModel
        : defaultModel && modelAvailableForCapability(globalConfig, defaultModel, mode)
            ? defaultModel
            : fallbackModel;
    return {
        ...globalConfig,
        model,
        quality: node.metadata?.quality || globalConfig.quality || defaultConfig.quality,
        size: node.metadata?.size || globalConfig.size || defaultConfig.size,
        videoSeconds: node.metadata?.seconds || globalConfig.videoSeconds || defaultConfig.videoSeconds,
        vquality: node.metadata?.vquality || globalConfig.vquality || defaultConfig.vquality,
        videoGenerateAudio: node.metadata?.generateAudio || globalConfig.videoGenerateAudio || defaultConfig.videoGenerateAudio,
        videoWatermark: node.metadata?.watermark || globalConfig.videoWatermark || defaultConfig.videoWatermark,
        audioVoice: node.metadata?.audioVoice || globalConfig.audioVoice || defaultConfig.audioVoice,
        audioFormat: node.metadata?.audioFormat || globalConfig.audioFormat || defaultConfig.audioFormat,
        audioSpeed: node.metadata?.audioSpeed || globalConfig.audioSpeed || defaultConfig.audioSpeed,
        audioInstructions: node.metadata?.audioInstructions || globalConfig.audioInstructions || defaultConfig.audioInstructions,
        count: String(node.metadata?.count || (mode === "image" ? globalConfig.canvasImageCount || globalConfig.count : globalConfig.count) || defaultConfig.count),
    };
}

function promptPlaceholder(
    mode: CanvasNodeGenerationMode,
    hasImageContent: boolean,
    hasTextContent: boolean,
    imageFeature: CanvasXiaohaImageFeature,
    featureLabel: string,
    hasRequiredReference: boolean,
) {
    if (mode === "video") return "描述要生成的视频内容";
    if (mode === "audio") return "描述要生成的音频内容";
    if (mode === "image" && !hasImageContent) return "请先上传或生成一张待处理原图";
    if (mode === "image" && !hasRequiredReference) return `${featureLabel}需要把至少 1 张参考图连接到当前图片节点`;
    if (imageFeature === "modelHd") return "可选：补充模特高清要求；人物、肤色、色调和构图会保持不变";
    if (imageFeature === "ai_qa_image") return "请输入你希望 AI 结合图片完成的生图要求";
    if (mode === "image") return `可选：补充${featureLabel}要求`;
    return hasTextContent ? "请输入你想要将本段文本修改成什么" : "请输入你想要生成的文本内容";
}

function OutpaintSettingsButton({ node, onConfigChange }: Pick<CanvasNodePromptPanelProps, "node" | "onConfigChange">) {
    const values = {
        top: Number(node.metadata?.outpaintTop ?? 100),
        bottom: Number(node.metadata?.outpaintBottom ?? 100),
        left: Number(node.metadata?.outpaintLeft ?? 100),
        right: Number(node.metadata?.outpaintRight ?? 100),
    };
    const field = (label: string, key: "outpaintTop" | "outpaintBottom" | "outpaintLeft" | "outpaintRight", value: number) => (
        <label className="grid grid-cols-[34px_1fr] items-center gap-2 text-xs">
            <span>{label}</span>
            <InputNumber
                min={0}
                max={30000}
                step={50}
                value={value}
                onChange={(nextValue) => onConfigChange(node.id, { [key]: Number(nextValue || 0) })}
            />
        </label>
    );
    return (
        <Popover
            trigger="click"
            placement="topRight"
            content={(
                <div className="grid w-44 gap-2" onMouseDown={(event) => event.stopPropagation()}>
                    <div className="text-xs font-medium">扩图像素</div>
                    {field("上", "outpaintTop", values.top)}
                    {field("下", "outpaintBottom", values.bottom)}
                    {field("左", "outpaintLeft", values.left)}
                    {field("右", "outpaintRight", values.right)}
                </div>
            )}
        >
            <Button className="!size-8 !min-w-8 !rounded-lg !p-0" aria-label="扩图设置" icon={<Settings2 className="size-4" />} />
        </Popover>
    );
}

function videoConfigPatch(key: keyof AiConfig, value: string) {
    if (key === "videoSeconds") return { seconds: value };
    if (key === "videoGenerateAudio") return { generateAudio: value };
    if (key === "videoWatermark") return { watermark: value };
    return { [key]: value };
}

function audioConfigPatch(key: CanvasAudioSettingKey, value: string) {
    if (key === "audioVoice") return { audioVoice: value };
    if (key === "audioFormat") return { audioFormat: value };
    if (key === "audioSpeed") return { audioSpeed: value };
    return { audioInstructions: value };
}
